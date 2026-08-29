# This is a sample Python script.

# Valuation game, v1.0
# By Marcelo Olivares
# First version: 10/04/2021

from io import StringIO
import os
import random
import numpy as np
import pandas as pd
import datetime
import csv

from flask import Flask, render_template, request, redirect, url_for
from flask import request, make_response

from sqlalchemy import create_engine, text

from bokeh.embed import components
from bokeh.plotting import figure
from bokeh.resources import INLINE
from bokeh.models import ColumnDataSource, Legend, HoverTool
from bokeh.layouts import column
from bokeh.palettes import Category10, Category20, inferno


app = Flask(__name__)

FILEVALUATIONS = "valuations.txt"

NPERIODS = 5                # Number of weeks in simulation
NPERIODS_HIGH = 1           # Number of weeks with high valuation in price discrimination setting

#------ DEFINE GAME TYPES --------------------
GAMETYPES = ['base','inv','disc']  # game types available

# Dictionary specifying if game type has inventory
HASINV = {'base':False,'inv':True,'disc':True}
INITINV = 40                # initial inventory for scenarios with inventory

# Dictionary specifiying the distribution on each period for each game type
GAMEVALUES = {'base':['full']*NPERIODS,
              'inv':['full']*NPERIODS,
              'disc':['low']*(NPERIODS-NPERIODS_HIGH)+['high']*NPERIODS_HIGH}
GAMENAMES = {'base': 'No inventory',
             'inv': 'Inventory',
             'disc': 'Inventory+Price discrim.'}
HIGHVALUE_CUT = 0.2
NUMCUST_LOW = 10
NUMCUST_HIGH = 20
SEED = 1975   # fallback seed used for games created before per-game seeds existed

# Header for the game types
GAMEHEADER = {
    'base': f"""Welcome to the valuation game! You will be selling a product during {NPERIODS} weeks.
                A random number of customers between 10-20 will arrive each week and will purchase the product if their willingness to pay is above the price.
                You can adjust prices every week, and the objective is to maximize revenue.""",
    'inv': f"""The game setup is similar: you will be selling a product during {NPERIODS} weeks adjusting the price every week.
                However, you have an initial inventory of {INITINV} units which limits the number of products that can be sold throughout the periods.
                The objective is to maximize revenue.""",
    'disc': f"""As before, you will be selling a product during {NPERIODS} weeks, adjusting the price every week with an initial inventory of {INITINV} units.
                However, in this scenario, the valuation of customers will vary across weeks. During the last week (week={NPERIODS}), only the top 20% of customers with the higher valuations will arrive.
                Customers with lower valuations will arrive on weeks 1 to {NPERIODS-1}.
                The objective is to maximize revenue."""
}

# ----------------------------------------------

#----------- VALUATIONS: default pool + per-game generation -------------------
# The default pool of valuations (used unless a game admin uploads a custom
# file at game-creation time). Kept as raw text so it can be parsed the same
# way as an uploaded file.
with open(FILEVALUATIONS) as valfile:
    DEFAULT_VALUATIONS_TEXT = valfile.read()


def load_valuation_list(text_blob):
    """Parse a newline-separated list of numbers into a sorted list of floats."""
    values = []
    for line in text_blob.splitlines():
        line = line.strip()
        if not line:
            continue
        values.append(float(line))
    values.sort()
    return values


DEFAULT_VALDIST = load_valuation_list(DEFAULT_VALUATIONS_TEXT)


def build_value_dist(valdist):
    """Split a sorted valuation pool into the 'full'/'high'/'low' subsets used
    by the different game types."""
    numobs = len(valdist)
    numcut = int(np.floor(numobs * (1 - HIGHVALUE_CUT)))
    return {
        'full': valdist,
        'high': valdist[numcut:(numobs - 1)],
        'low': valdist[0:numcut],
    }


def generate_valuations(seed, valdist):
    """Deterministically generate the per-week customer valuations for every
    game type, given a random seed and a (sorted) pool of valuations. Uses a
    local RNG instance so concurrent requests for different games never
    interfere with each other."""
    value_dist = build_value_dist(valdist)
    rng = random.Random(seed)
    valuations = {}
    for g in GAMETYPES:
        weekly = []
        for n in range(NPERIODS):
            valtype = GAMEVALUES[g][n]
            ncust = rng.randint(NUMCUST_LOW, NUMCUST_HIGH)
            weekly.append(rng.choices(value_dist[valtype], k=ncust))
        valuations[g] = weekly
    return valuations


# Per-gameid caches: a game's seed/valuations are immutable once created, so
# recomputing them from the stored (seed, valuations_text) is safe to cache
# in-process (and safe across gunicorn worker processes, since each worker
# recomputes the identical result from the same stored inputs).
_game_record_cache = {}
_game_valuations_cache = {}


def get_game_record(gameid):
    gameid = int(gameid)
    if gameid in _game_record_cache:
        return _game_record_cache[gameid]
    with engine.connect() as con:
        row = con.execute(text("SELECT seed, valuations_text FROM games WHERE gameid=:gid"),
                           {"gid": gameid}).fetchone()
    if row is None:
        record = (SEED, None)  # unknown/legacy game: fall back to the original fixed sequence
    else:
        seed, valuations_text = row
        record = (seed if seed is not None else SEED, valuations_text)
    _game_record_cache[gameid] = record
    return record


def get_game_valuations(gameid):
    """Return {gametype: [[valuations per week], ...]} for this game, using
    its stored seed and (optionally custom-uploaded) valuations pool."""
    gameid = int(gameid)
    if gameid in _game_valuations_cache:
        return _game_valuations_cache[gameid]
    seed, valuations_text = get_game_record(gameid)
    valdist = load_valuation_list(valuations_text) if valuations_text else DEFAULT_VALDIST
    valuations = generate_valuations(seed, valdist)
    _game_valuations_cache[gameid] = valuations
    return valuations


# ----------- DATABASE ----------------------------
# Uses Postgres in production (via Heroku's DATABASE_URL) and falls back to a
# local SQLite file when DATABASE_URL isn't set, so local development needs
# no extra setup.
DATABASE = 'gameresults.sqlite'
DATABASE_URL = os.environ.get("DATABASE_URL", f"sqlite:///{DATABASE}")
if DATABASE_URL.startswith("postgres://"):
    # Heroku's older-style URL scheme isn't accepted by modern SQLAlchemy.
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)

with engine.begin() as con:
    con.execute(text("""CREATE TABLE IF NOT EXISTS results
                     (timestamp text, gameid text, gametype text, groupid text,
                      period integer, price real, ncust integer, sales integer, end_inv integer)"""))
    con.execute(text("""CREATE TABLE IF NOT EXISTS games
                    (gameid integer, gamestatus text, timestamp text)"""))

# Add the columns needed for per-game valuations to games tables created
# before this feature existed. Neither SQLite nor Postgres support
# "ADD COLUMN IF NOT EXISTS" identically (SQLite doesn't support it at all),
# and on Postgres a failed statement poisons the rest of its transaction, so
# each attempt gets its own transaction and any "already exists" error from
# it alone is swallowed.
for _ddl in ("ALTER TABLE games ADD COLUMN seed INTEGER",
             "ALTER TABLE games ADD COLUMN valuations_text TEXT"):
    try:
        with engine.begin() as con:
            con.execute(text(_ddl))
    except Exception:
        pass  # column already exists


# ------------ APP FUNCTIONS -------------------------

@app.route('/login')
def login():
    return render_template('login.html')


# -------------- AUXILIARY FUNCTIONS ------------------------

def get_sales(pricenum,values):
    """Calculate sales for the submitted (numeric) price"""
    sales = 0
    for i in range(len(values)):
        sales = sales + (values[i]>=pricenum)
    return str(sales)

def get_sales_hist(price_list,init_inv,valuations):
    if init_inv:
        invnum = int(init_inv)
    else:
        invnum = float("inf")

    tperiod = len(price_list)
    sales_list = []
    ncust_list = []
    for t in range(tperiod):
        salesnum = min( int(get_sales(price_list[t],valuations[t])), invnum)
        invnum = invnum - salesnum
        sales_list.append(salesnum)
        ncust_list.append(len(valuations[t]))
    sales_arr = np.array(sales_list)
    ncust_arr = np.array(ncust_list)
    return sales_arr, ncust_arr

def csvstr_to_numarr(csv_str):
    if csv_str:
        return list(map(float, csv_str.split(',')))
    return []

def get_active_games():
    with engine.connect() as con:
        df = pd.read_sql(text("SELECT * FROM games WHERE gamestatus='open'"), con=con)
    return list(df['gameid'])

#----------------------------


@app.route('/maingame', methods=['POST'])
def maingame():
    # Get parameters from POST request
    gameid = request.form.get("gameid")
    groupname = request.form.get("groupname")
    gametype = request.form.get("gametype", "base")  # Default to "base" if not provided
    # Get the game header for the selected game type
    game_header = GAMEHEADER.get(gametype, "")

    # Set initial inventory if game type requires it
    if HASINV[gametype]:
        init_inv = INITINV
    else:
        init_inv = None

    hasinv = 1 if init_inv is not None else 0

    # Fetch the valuation types for the current game type
    valuetype_array = GAMEVALUES[gametype]

    # This game's own valuations (default pool, or a custom uploaded one)
    game_valuations = get_game_valuations(gameid)

    # Initialize Bokeh sources as before
    price_list = [None] * 5
    x_values = [str(i) for i in range(1, 6)]
    price_source = ColumnDataSource(data=dict(x=x_values, y=price_list), name="price_data_source")

    # Create Bokeh plots (similar to previous code)
    p_price = figure(
        title="Price History",
        height=250,
        toolbar_location=None,
        x_axis_label="Week",
        y_axis_label="Price",
        x_range=x_values,
        name="price_plot"
    )
    p_price.line('x', 'y', source=price_source, line_width=2)
    p_price.circle('x', 'y', source=price_source, fill_color='white', size=8)

    bar_data = {
        'week': x_values,
        'sales': [0] * 5,
        'no_purchase': [0] * 5,
        'customers': [0] * 5,
        'fraction': [0] * 5,
    }
    bar_source = ColumnDataSource(data=bar_data, name="bar_data_source")

    colors = ["#718dbf", "#e84d60"]
    p_bar = figure(
        height=250,
        x_range=x_values,
        toolbar_location=None,
        title="Number of Customers and Sales per Week",
        x_axis_label="Week",
        y_axis_label="Demand (units)"
    )
    p_bar.vbar_stack(['sales', 'no_purchase'], x='week', width=0.9, color=colors, source=bar_source, legend_label=['Sales', 'No Purchase'])
    hover = HoverTool(tooltips=[('#Customers', '@customers'), ('Frac. Purchase', '@fraction')])
    p_bar.add_tools(hover)
    p_bar.xgrid.grid_line_color = None
    p_bar.y_range.start = 0
    p_bar.legend.location = "top_right"
    p_bar.legend.orientation = "horizontal"

    script, divs = components((p_price, p_bar))
    js_resources = INLINE.render_js()
    css_resources = INLINE.render_css()

    return render_template(
        'maingame.html',
        plot_script=script,
        plot_div=divs[0] + divs[1],
        js_resources=js_resources,
        css_resources=css_resources,
        valuations=game_valuations[gametype],
        init_inv=init_inv if hasinv else None,
        hasinv=hasinv,
        gameid=gameid,
        groupname=groupname,
        gametype=gametype,
        game_header=game_header,  # Pass the header text to the HTML template
        currentWeek=1,
        valuetype_array=valuetype_array  # Pass the valuetype array to the HTML
    )


@app.route("/results/<string:gametype>", methods=['POST'])
def send_results(gametype):
    global GAMETYPES, HASINV

    if gametype not in GAMETYPES:
        return "<h2> URL not found </h2>"

    init_inv = INITINV if HASINV[gametype] else None

    gameid_str = request.form.get("gameid")
    groupid = request.form.get("groupname")
    gameid = int(gameid_str)

    game_valuations = get_game_valuations(gameid)

    # Only the submitted price sequence is trusted from the client. Sales,
    # customer counts and ending inventory are always recomputed here from
    # the game's authoritative valuations, so a student can't inflate their
    # revenue by editing the page before submitting.
    price_hist_str = request.form.get("price_hist")
    price_hist = list(map(float, price_hist_str.split(',')))[:NPERIODS] if price_hist_str else []

    sales_arr, ncust_arr = get_sales_hist(price_hist, init_inv, game_valuations[gametype])
    if init_inv:
        end_inv = (init_inv - np.cumsum(sales_arr)).tolist()
    else:
        end_inv = [None] * len(price_hist)

    currtime = datetime.datetime.now()
    df = gen_results_table(
        timestamp=str(currtime),
        gameid=gameid_str,
        gametype=gametype,
        groupid=groupid,
        price_hist=price_hist,
        ncust=ncust_arr.tolist(),
        sales=sales_arr.tolist(),
        end_inv=end_inv
    )

    is_update = False
    try:
        with engine.begin() as con:
            existing = con.execute(
                text("SELECT COUNT(*) FROM results WHERE gameid=:gid AND gametype=:gt AND groupid=:grp"),
                {"gid": gameid_str, "gt": gametype, "grp": groupid}
            ).scalar()
            is_update = existing > 0
            if is_update:
                # A submission for this group/round already exists: replace
                # it rather than appending, so results can't be inflated by
                # submitting more than once.
                con.execute(
                    text("DELETE FROM results WHERE gameid=:gid AND gametype=:gt AND groupid=:grp"),
                    {"gid": gameid_str, "gt": gametype, "grp": groupid}
                )
            df.to_sql('results', con=con, if_exists='append', index=False)
        saved = True
    except Exception as e:
        saved = False
        error_msg = str(e)

    if saved:
        # Determine the next game type
        currgame_index = GAMETYPES.index(gametype)
        nextgame = GAMETYPES[currgame_index + 1] if currgame_index < len(GAMETYPES) - 1 else None

        return render_template("result_confirm.html", tables=[df.to_html(classes='data', header="true")],
                               nextgame=nextgame, gameid=gameid_str, groupname=groupid,
                               is_update=is_update)
    else:
        return f"<h1> Error: results could not be saved</h1>{error_msg}"

def gen_results_table(timestamp, gameid, gametype, groupid, price_hist, ncust, sales, end_inv=None):
    """Calculates results table from price_hist and other lists"""

    # Convert price_hist from a CSV string to a list of floats if it’s not already a list
    if isinstance(price_hist, str):
        price = list(map(float, price_hist.split(',')))
    else:
        price = price_hist

    # If end_inv is not provided, fill it with None values to match the length of other lists
    if end_inv is None:
        end_inv = [None] * len(price)

    # Ensure all lists have the same length by determining the minimum length
    min_length = min(len(price), len(ncust), len(sales), len(end_inv))
    if len(price) != min_length or len(ncust) != min_length or len(sales) != min_length or len(end_inv) != min_length:
        print(f"Adjusting lists to minimum length of {min_length}")
        price = price[:min_length]
        ncust = ncust[:min_length]
        sales = sales[:min_length]
        end_inv = end_inv[:min_length]

    # Confirm lists are now of equal length
    if len(price) == len(ncust) == len(sales) == len(end_inv):
        print("All lists are of equal length and ready for DataFrame creation.")
    else:
        raise ValueError("All lists must be of the same length.")

    # Construct DataFrame
    data = {
        'timestamp': [timestamp] * min_length,
        'gameid': [gameid] * min_length,
        'gametype': [gametype] * min_length,
        'groupid': [groupid] * min_length,
        'period': list(range(1, min_length + 1)),
        'price': price,
        'ncust': ncust,
        'sales': sales,
        'end_inv': end_inv,
    }

    df = pd.DataFrame(data)
    return df


#------------------------------------------------------------

#------------- DASHBOARD ----------------------------
@app.route('/dashboard', methods=['POST','GET'])
def results_dashboard():
    isnew = 0   # default is an existing game
    upload_error = None
    if request.method == 'POST':
        gameid_str = request.form.get('gameid')
        gametype = request.form.get('gametype')
        isnew_str = request.form.get('isnew')
        if isnew_str:
            isnew = int(isnew_str)
    else:
        gameid_str = request.args.get('gameid')
        gametype = request.args.get('gametype')

    gameid = int(gameid_str)

    if isnew == 1:  # if new game, insert into database as open game, with its own seed/valuations
        seed = random.randint(1, 2**31 - 1)
        valuations_text = None

        uploaded = request.files.get('valuations_file')
        if uploaded and uploaded.filename:
            raw = uploaded.read().decode('utf-8', errors='ignore')
            try:
                parsed = load_valuation_list(raw)
                if len(parsed) < 5:
                    raise ValueError("file must contain at least 5 valuations")
                valuations_text = raw
            except Exception as e:
                upload_error = (f"Could not use the uploaded valuations file ({e}); "
                                 f"this game will use the default valuations instead.")

        currtime = datetime.datetime.now()
        with engine.begin() as con:
            con.execute(text("""INSERT INTO games (gameid, gamestatus, timestamp, seed, valuations_text)
                                 VALUES (:gameid, 'open', :ts, :seed, :vtext)"""),
                        {"gameid": gameid, "ts": str(currtime), "seed": seed, "vtext": valuations_text})

    # get list of open games
    gamelist = get_active_games()

    fig1 = draw_results_allgroups(gameid= gameid, gametype= gametype)
    fig1.sizing_mode='scale_width'
    fig2 = overall_standing(gameid= gameid)
    fig2.sizing_mode='scale_width'

    # grab the static resources
    js_resources = INLINE.render_js()
    css_resources = INLINE.render_css()
    # render template
    # scale to container size
    fig = column(fig1, fig2,sizing_mode='scale_width')
    script, div = components(fig)

    html = render_template('results_dashboard.html',
                           gameid= gameid,
                           gametype= gametype,
                           typelist = GAMETYPES,
                           gamelist = gamelist,
                           plot_script=script,
                           plot_div=div,
                           js_resources=js_resources,
                           css_resources=css_resources,
                           upload_error=upload_error
                           )
    return (html)


@app.route('/adminLogin')
def admin_login():
    # Retrieve open games from table
    gamelist = get_active_games()
    # first game id to try
    newgameid = 12345

    while newgameid in gamelist:
        newgameid = random.randint(10000, 99999)
    html = render_template('login_admin.html',
                           newgameid = newgameid,
                           gamelist = gamelist)
    return(html)


@app.route('/get_results')
def retrieve_results():
    with engine.connect() as con:
        df = pd.read_sql(text("SELECT * FROM results"), con=con)
    return(df.to_html())


def draw_results_allgroups(gameid, gametype):
    with engine.connect() as con:
        df = pd.read_sql(text("SELECT * FROM results WHERE gameid=:gid AND gametype=:gt"),
                          con=con, params={"gid": str(gameid), "gt": gametype})
    names = df['groupid'].unique()
    colors = color_gen(len(names))
    p = figure(aspect_ratio=2.0, sizing_mode="scale_width",
               toolbar_location='above', title="Price history for all groups",
               tools="pan,wheel_zoom,box_zoom,reset")

    p_dict = dict()
    p_circ_dict = dict()
    for n,c in zip(names,colors):
        source = ColumnDataSource(data=df.loc[df['groupid']==n])
        p_dict[n] = p.line(x='period',y='price', source=source, color=c, hover_line_width=3 )
        p_circ_dict[n] = p.circle(x='period', y='price', fill_color=c, size=5, source=source)

    # add hover
    hover = HoverTool(tooltips=[('Group','@groupid'),('Price','@price')],
                      renderers= list(p_dict.values()) )
    p.add_tools(hover)

    # Create legend
    legend_items = [(x, [p_dict[x]]) for x in p_dict]
    legend = Legend(items=legend_items, label_text_font_size='16pt')
    p.add_layout(legend,'right')
    p.legend.click_policy = "hide"
    p.xaxis.axis_label = 'Week'
    p.xaxis.axis_label_text_font_size = '18pt'
    p.xaxis.major_label_text_font_size = '16pt'
    p.yaxis.axis_label = 'Price'
    p.yaxis.axis_label_text_font_size = '18pt'
    p.yaxis.major_label_text_font_size = '14pt'

    return p

def overall_standing(gameid):
    with engine.connect() as con:
        df = pd.read_sql(text("""SELECT groupid, gametype, sum(price*sales) AS revenue
                                 FROM results
                                 WHERE gameid=:gid
                                 GROUP BY groupid, gametype"""),
                          con=con, params={"gid": str(gameid)})

    if df['revenue'].count()==0:
        # No groups have send their results. Display empty figure.
        return figure(height=250,
               toolbar_location=None, title="No results registered")

    games = list(df['gametype'].unique())
    colors = color_gen(len(games))

    # Calculate total revenue to sort
    totrevenue = df.groupby("groupid", as_index=False)['revenue'].sum()
    totrevenue.sort_values(by=['revenue'], inplace=True)
    names = totrevenue['groupid'].unique()

    # Pivot table to create stacked chart
    df2 = df.pivot(index='groupid', columns='gametype', values='revenue').reset_index()
    df2 = df2.fillna(0)
    df2['revenue']= df2[games].sum(axis=1)

    source = ColumnDataSource(df2)

    p = figure(height=250, y_range = names,
               toolbar_location='above', title="Overall standing",
               tools="pan,wheel_zoom,box_zoom,reset")
    v = p.hbar_stack(games, y='groupid', height=0.8, source=source, color=colors)

    # add hover
    tooltips = [(game, f'@{game}{{0.0}}') for game in games]
    hover = HoverTool(tooltips=tooltips)
    p.add_tools(hover)

    legend = Legend(items=[(GAMENAMES[games[x]], [v[x]]) for x in range(len(games))],
                    label_text_font_size='16pt')
    p.add_layout(legend,'right')

    p.yaxis.major_label_text_font_size = '16pt'

    return p

@app.route('/download_results', methods=['POST'])
def download_table():
    # Get input values from form
    filter_value = request.form['gameid']

    with engine.connect() as con:
        result = con.execute(text("SELECT * FROM results WHERE gameid=:gid"), {"gid": filter_value})
        rows = result.fetchall()
        cols = list(result.keys())

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(cols)
    for row in rows:
        writer.writerow(row)

    response = make_response(output.getvalue())
    response.headers['Content-Disposition'] = f'attachment; filename=results_{filter_value}.csv'
    response.headers['Content-Type'] = 'text/csv'

    return response

def color_gen(ncolors):
    """ generates list of colors for bokeh graph"""
    if ncolors < 3:
        colorlist = Category10[3][0:ncolors]
    elif ncolors <= 10:
        colorlist = Category10[ncolors]
    elif ncolors <= 20:
        colorlist = Category20[ncolors]
    else:
        colorlist = inferno(ncolors)
    return colorlist


@app.route('/manage_games', methods=['GET', 'POST'])
def manage_games():
    active_games = [str(game) for game in get_active_games()]  # Ensure all game IDs are strings
    selected_gameid = None
    game_results = pd.DataFrame()

    if request.method == 'POST':
        selected_gameid = str(request.form.get('gameid'))  # Convert selected game ID to string

        # Handle filtering
        if 'filter' in request.form and selected_gameid:
            with engine.connect() as con:
                game_results = pd.read_sql(text("SELECT * FROM results WHERE gameid = :gid"),
                                           con, params={"gid": selected_gameid})

        # Handle deletion
        elif 'delete' in request.form and selected_gameid:
            with engine.begin() as con:
                con.execute(text("DELETE FROM results WHERE gameid = :gid"), {"gid": selected_gameid})
                con.execute(text("DELETE FROM games WHERE gameid = :gid"), {"gid": int(selected_gameid)})
            return redirect(url_for('manage_games'))

    return render_template(
        'manage_games.html',
        active_games=active_games,
        selected_gameid=selected_gameid,
        game_results=game_results.to_dict(orient='records')
    )


# ------------- RUN APP ----------------------------

# for testing
#if __name__ == '__main__':
#    app.run(debug=True, port=5000)


# Following line is to run locally
if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8080, debug=True)

#if __name__ == "__main__":
    # Use the following when deploying with Procfile using gunicorn
    # See: https: // dev.to / lordofdexterity / deploying - flask - app - on - heroku - using - github - 50
    # Procfile >> web: gunicorn --bind 0.0.0.0:$PORT main:app (This is the Procfile)
#    app.run(debug=True) # final deployment set debug=False

    # The following can be used when Procfile uses python directly:
    # (see https://www.youtube.com/watch?v=OUXzdPnh6wI )
    # Procfile >> web: python main.py (this is the Procfile)
    # Use the following to run with the "python" Procfile.
    # port = os.environ.get("PORT",5000) # Requires the os library.
    # app.run(debug=True,host="0.0.0.0,port=port)
