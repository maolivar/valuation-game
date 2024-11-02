# This is a sample Python script.

# Valuation game, v1.0
# By Marcelo Olivares
# First version: 10/04/2021

from io import StringIO
import random
import base64
import numpy as np
import pandas as pd
import sqlite3 as sql
import datetime
import itertools
import csv

#from io import BytesIO

from flask import Flask, render_template, request, redirect, url_for
from flask import request, make_response
from matplotlib.figure import Figure

from bokeh.embed import components
from bokeh.plotting import figure
from bokeh.resources import INLINE
from bokeh.models import ColumnDataSource, Range1d, Legend, HoverTool,CustomJS, CheckboxGroup
from bokeh.core.properties import value
from bokeh.layouts import column, row
from bokeh.palettes import Category10, Category20, inferno





app = Flask(__name__)

FILEVALUATIONS = "valuations.txt"
DATABASE = 'gameresults.sqlite' # Database file to store results

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
SEED = 1975

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

#----------- GENERATE VALUATIONS FOR EACH GAME TYPE -------------------
valfile = open(FILEVALUATIONS)
val_list = valfile.readlines()

valdist = list(map(int, val_list))  # map() applies function int() to each item in val_list
valdist.sort()
numobs = len(valdist)
numcut = int(np.floor(numobs*(1-HIGHVALUE_CUT)))

VALUEDIST = {}
VALUEDIST['full'] = valdist
VALUEDIST['high'] = valdist[numcut:(numobs-1)]
VALUEDIST['low'] = valdist[0:numcut]

VALUATIONS = {}
random.seed(SEED)

for g in GAMETYPES:
    valuations = []
    for n in range(NPERIODS):
        valtype = GAMEVALUES[g][n]
        ncust = random.randint(NUMCUST_LOW,NUMCUST_HIGH)
        valuations.append(random.choices(VALUEDIST[valtype], k = ncust))
    VALUATIONS[g] = valuations


# CREATE TABLES IF THEY DON'T EXIST

con = sql.connect(DATABASE)
cur = con.cursor()
#
# # Create results table
cur.execute("""CREATE TABLE IF NOT EXISTS results
                 (timestamp text, gameid text, gametype text, groupid text,
                  period integer, price real, ncust integer, sales integer, end_inv integer)""")
cur.execute("""CREATE TABLE IF NOT EXISTS games 
                (gameid integer, gamestatus text, timestamp text)""")
con.commit()
con.close()


# ------------ APP FUNCTIONS -------------------------

@app.route('/login')
def login():
    #return ("""<h2> This is the login page </h2>""")
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

def draw_graph(price_hist, init_inv,valuations):
    global NPERIODS
    XMAX = NPERIODS +2  # length of the x-axis, extended to put label
    price_list= csvstr_to_numarr(price_hist)
    price_arr = np.array(price_list)
    x = list(range(1,len(price_list)+1))
    fig = Figure()
   # ax = fig.subplots()
    ax = fig.add_subplot(211)
 #   ax.set_xlabel('week')
    ax.set_ylabel('price')
    ax.set_xlim(xmin=0, xmax=XMAX)
    ax.set_xticks(list(range(1,NPERIODS+1)))
    ax.set_title('Price history')
    ax.plot(x, price_list)
    ax.scatter(x, price_list)

    (sales_arr,ncust_arr) = get_sales_hist(price_list, init_inv,valuations)
    lostsales_arr = ncust_arr - sales_arr
    ax2 = fig.add_subplot(212)
    ax2.bar(x, sales_arr, label='Sales')
    ax2.bar(x, lostsales_arr, bottom=sales_arr, label="No purchase")
    ax2.set_xlabel('week')
    ax2.set_ylabel('customers')
    ax2.legend(loc='center right')
    ax2.set_xlim(xmin=0, xmax=XMAX)
    ax2.set_xticks(list(range(1,NPERIODS+1)))
    ax2.set_title('Sales history')

    fig.tight_layout()

    return fig

from bokeh.models import ColumnDataSource, CustomJS, HoverTool
from bokeh.plotting import figure
from bokeh.embed import components
from bokeh.resources import INLINE



def draw_bokeh_graph(price_hist, init_inv, valuations):

    global NPERIODS
    XMAX = NPERIODS + 2  # length of the x-axis, extended to put label
    price_list = csvstr_to_numarr(price_hist)
    price_arr = np.array(price_list)
    x = list(map(str,range(1, len(price_list) + 1)))
    weeks = list(map(str,range(1,NPERIODS+1)))

    # Graph 1: price history
    g = figure( height=250, x_range= weeks,
                toolbar_location=None, title="Price history")
    price_line = g.line(x,price_arr, line_width=2)
    price_circ = g.circle(x,price_arr, fill_color='white', size=8)

    # add hover
    hover1 = HoverTool(tooltips=[('Price', '@y')],
                      renderers=[price_circ])
    g.add_tools(hover1)

    g.xaxis.axis_label = "Week"
    g.yaxis.axis_label = "Price"
    g.axis.minor_tick_line_color = None
    g.outline_line_color = None
    g.xgrid.grid_line_color = None

    # Figure 2: bar graph of sales and lost sales
    (sales_arr, ncust_arr) = get_sales_hist(price_list, init_inv, valuations)
    lostsales_arr = ncust_arr - sales_arr

    colstack = ['sales','no purchase']
    data = {'week':x,
            'sales': sales_arr,
            'no purchase':lostsales_arr,
            'customers': ncust_arr,
            'fraction':sales_arr/ncust_arr}

    colors = ["#718dbf", "#e84d60"]

    source = ColumnDataSource(data=data)

    p = figure( height=250, x_range= weeks,
                toolbar_location=None, title="Number of customers and sales per week")

    p.vbar_stack(colstack, x='week', width=0.9, color=colors, source=source, legend_label=colstack)
    # add hover
    hover2 = HoverTool(tooltips=[('#customers', '@customers'),('Frac.Purchase','@fraction')])
    p.add_tools(hover2)
    p.x_range.range_padding = 0.1
    p.xgrid.grid_line_color = None
    p.y_range.start = 0
    p.y_range.end = NUMCUST_HIGH + 5
    p.legend.location = "top_right"
    p.legend.orientation = "horizontal"
    p.axis.minor_tick_line_color = None
    p.outline_line_color = None
    p.xaxis.axis_label = "Week"
    p.yaxis.axis_label = "Demand (units)"

    return column(g,p)

def get_active_games():
    with  sql.connect(DATABASE) as con:
        df = pd.read_sql("""SELECT * FROM games WHERE gamestatus='open'""", con=con)
    return list(df['gameid'])

#----------------------------




#### ----------------- NEW CODE ----------------------------

from bokeh.resources import INLINE

from flask import Flask, render_template
from bokeh.plotting import figure
from bokeh.embed import components
from bokeh.models import ColumnDataSource
from bokeh.resources import INLINE

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
        valuations=VALUATIONS[gametype],  # Assume valuations set elsewhere
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
    global VALUATIONS, GAMETYPES, HASINV

    valuations = VALUATIONS[gametype]
    if not gametype in GAMETYPES:
        return "<h2> URL not found </h2>"
    elif HASINV[gametype]:
        init_inv = INITINV
    else:
        init_inv = None

    # Retrieve form data
    price_hist_str = request.form.get("price_hist")
    ncust_str = request.form.get("ncust")
    sales_str = request.form.get("sales")
    end_inv_str = request.form.get("end_inv")

    # Convert to lists
    price_hist = list(map(float, price_hist_str.split(','))) if price_hist_str else []
    ncust = list(map(int, ncust_str.split(','))) if ncust_str else []
    sales = list(map(int, sales_str.split(','))) if sales_str else []
    end_inv = [int(x) if x else None for x in end_inv_str.split(',')] if end_inv_str else [None] * len(price_hist)

    # Ensure lengths match
    min_length = min(len(price_hist), len(ncust), len(sales), len(end_inv))
    price_hist = price_hist[:min_length]
    ncust = ncust[:min_length]
    sales = sales[:min_length]
    end_inv = end_inv[:min_length]

    # Generate results table
    currtime = datetime.datetime.now()
    df = gen_results_table(
        timestamp=str(currtime), 
        gameid=request.form.get("gameid"), 
        gametype=gametype, 
        groupid=request.form.get("groupname"),
        price_hist=price_hist, 
        ncust=ncust, 
        sales=sales, 
        end_inv=end_inv
    )

    # Save the DataFrame to the database
    try:
        with sql.connect(DATABASE) as con:
            df.to_sql('results', con=con, if_exists='append', index=False)
            con.commit()
        saved = True
    except Exception as e:
        saved = False
        error_msg = str(e)

    if saved:
        # Determine the next game type
        currgame_index = GAMETYPES.index(gametype)
        nextgame = GAMETYPES[currgame_index + 1] if currgame_index < len(GAMETYPES) - 1 else None
        
        return render_template("result_confirm.html", tables=[df.to_html(classes='data', header="true")], nextgame=nextgame, gameid=request.form.get("gameid"), groupname=request.form.get("groupname"))
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

    if isnew == 1:  # if new game, insert into database as open game
        currtime = datetime.datetime.now()
        data = {'gameid': [gameid], 'gamestatus': ['open'], 'timestamp': [str(currtime)]}
        df = pd.DataFrame(data)
        with sql.connect(DATABASE) as con:
            df.to_sql('games', con=con, if_exists='append', index=False)
            con.commit()

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
    #fig = column(fig1, fig2, sizing_mode="scale_height")
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
                           css_resources=css_resources
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
    con = sql.connect(DATABASE)
    df = pd.read_sql('SELECT * FROM results', con=con)
    con.close()
    return(df.to_html())


def draw_results_allgroups(gameid, gametype):
    with  sql.connect(DATABASE) as con:
        df = pd.read_sql("""SELECT * FROM results WHERE gameid=%s AND gametype='%s'"""%(gameid, gametype), con=con)
    names = df['groupid'].unique()
    colors = color_gen(len(names))
    print(colors)
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
    # create the legend items
    legend_items = [(x, [p_dict[x]]) for x in p_dict]
    # create the legend
    legend = Legend(items=legend_items, label_text_font_size='16pt')

    #legend = Legend(items=[(x, [p_dict[x]]) for x in p_dict],
    #                label_text_font_size='16pt')
    p.add_layout(legend,'right')
    p.legend.click_policy = "hide"
    p.xaxis.axis_label = 'Week'
    p.xaxis.axis_label_text_font_size = '18pt'
    p.xaxis.major_label_text_font_size = '16pt'
    p.yaxis.axis_label = 'Price'
    p.yaxis.axis_label_text_font_size = '18pt'
    p.yaxis.major_label_text_font_size = '14pt'

    # TO DO
    # - Add sales for this round, bar graph
    # - Add hover tools
    return p

def overall_standing(gameid):
    with  sql.connect(DATABASE) as con:
        df = pd.read_sql("""SELECT groupid, gametype, sum(price*sales) AS revenue
                            FROM results
                            WHERE (gameid='%s')
                            GROUP BY groupid, gametype"""%(gameid), con=con)


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
    #hover = HoverTool(tooltips=[('Group', '@groupid'),('Total revenue','@revenue')])
    p.add_tools(hover)

    legend = Legend(items=[(GAMENAMES[games[x]], [v[x]]) for x in range(len(games))],
                    label_text_font_size='16pt')
    p.add_layout(legend,'right')

    p.yaxis.major_label_text_font_size = '16pt'

    return p

@app.route('/download_results', methods=['POST'])
#@app.route('/download_csv')
def download_table():
    # Get input values from form
    filter_value = request.form['gameid']
    #filter_value = '12345'

    # Connect to database
    conn = sql.connect(DATABASE)
    cursor = conn.cursor()

    # Construct SQL query with filter
    query = f"SELECT * FROM results WHERE gameid='{filter_value}'"

    # Retrieve data from database
    cursor.execute(query)
    rows = cursor.fetchall()
    cols = [desc[0] for desc in cursor.description]

    output = StringIO()
    writer = csv.writer(output)

    writer.writerow(cols)
    # write the query results to the CSV
    for row in rows:
        writer.writerow(row)
        print(row)

    response = make_response(output.getvalue())
    response.headers['Content-Disposition'] = f'attachment; filename=results_{filter_value}.csv'
    response.headers['Content-Type'] = 'text/csv'

    # Close database connection
    cursor.close()
    conn.close()

    return response

def color_gen(ncolors):
    """ generates list of colors for bokeh graph"""
    #yield from itertools.cycle(Category10[10])
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
            with sql.connect(DATABASE) as con:
                query = "SELECT * FROM results WHERE gameid = ?"
                game_results = pd.read_sql(query, con, params=(selected_gameid,))

        # Handle deletion
        elif 'delete' in request.form and selected_gameid:
            with sql.connect(DATABASE) as con:
                cur = con.cursor()
                # Delete from both tables
                cur.execute("DELETE FROM results WHERE gameid = ?", (selected_gameid,))
                cur.execute("DELETE FROM games WHERE gameid = ?", (selected_gameid,))
                con.commit()
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



# ----------------- OLD CODE ----------------------------

def gen_results_table_OLD(timestamp, gameid, gametype, groupid, price_hist, init_inv,valuations):
    """ Calculates results table from price_hist string"""
    price = csvstr_to_numarr(price_hist)
    (sales,ncust) = get_sales_hist(price, init_inv,valuations)
    cumsales = np.cumsum(sales)
    nperiods = len(price)
    period = np.array(range(1,nperiods+1))
    if init_inv:
        inventory = np.repeat(int(init_inv),nperiods) - cumsales
    else:
        inventory = np.repeat(None,nperiods)

    data = {'timestamp':timestamp,
             'gameid':gameid,
             'gametype':gametype,
            'groupid': groupid,
            'period':period,
            'price':price,
            'ncust':ncust,
            'sales':sales,
            'end_inv':inventory}

    df = pd.DataFrame(data)
    return df






@app.route("/<string:gametype>", methods = ['POST'])
def index(gametype):
    global NPERIODS, VALUATIONS, GAMETYPES, HASINV, GAMEVALUES

    gameid = request.form.get("gameid")
    groupname = request.form.get("groupname")
    gamelist = get_active_games()
    if int(gameid) not in gamelist:
        return ("""<h2> Invalid game password </h2> \n
                <a href ="/login" class="link_button"> Back to login </a>""")


    if not gametype in GAMETYPES:
        return("""<h2> URL not found </h2>""")
    elif not HASINV[gametype]:
        init_inv = None
        inventory = None
    else:
        init_inv = INITINV
        inventory = request.form.get("inv")

    valuations = VALUATIONS[gametype]

    price = request.form.get("price")
    stage = request.form.get("stage")
    price_hist = request.form.get("price_hist")

    if init_inv and inventory == None:
        # Sets inventory to initial inventory in the first stage
        inventory = init_inv

    if price and stage:     # this is passed after stage 1.
        stagenum = int(stage)
        sales = get_sales(float(price),valuations[stagenum-1])
        ncust = len(valuations[stagenum-1])
        salesnum = int(sales)

        if inventory == None:
            invnum = float("inf")
        else:
            invnum = int(inventory)

        salesnum = min(salesnum,invnum)
        invnum = invnum - salesnum
        sales = str(salesnum)

        if invnum < float("inf"):
            inventory = str(invnum)

        price_hist = price_hist+price+","
        stagenum = stagenum + 1
    else:                   # set the first stage
        price_hist=""
        stagenum = 1

    stage = str(stagenum)

    # Matplotlib graph
    #fig = draw_graph(price_hist,init_inv,valuations)
    # Save it to a temporary buffer.
    #buf = BytesIO()
    #fig.savefig(buf, format="png")
    # Embed the result in the html output.
    #data = base64.b64encode(buf.getbuffer()).decode("ascii")

    # Bokeh graph
    bfig = draw_bokeh_graph(price_hist, init_inv, valuations)
    # grab the static resources
    js_resources = INLINE.render_js()
    css_resources = INLINE.render_css()
    # render template
    script, div = components(bfig)

    if price_hist:
        # if there is price history, calculate revenues up to current stage
        price_arr = csvstr_to_numarr(price_hist)
        (sales_arr, ncust_arr) = get_sales_hist(price_arr, init_inv, valuations)
        totrevenue = np.dot(price_arr, sales_arr)

    if stagenum == 1:
        return render_template('welcome.html', gameid=gameid, groupname= groupname,
                               has_inv = HASINV[gametype],
                               valuetype = GAMEVALUES[gametype][stagenum-1],
                               value_list = GAMEVALUES[gametype],
                               typename=GAMENAMES[gametype],
                               stage = stage, inv = inventory,
                               nperiods = str(NPERIODS),
                               plot_script=script,
                               plot_div=div,
                               js_resources=js_resources,
                               css_resources=css_resources
                               )
    elif stagenum <= NPERIODS:
        return render_template('base.html', gameid=gameid, groupname= groupname,
                               has_inv = HASINV[gametype],
                               valuetype=GAMEVALUES[gametype][stagenum - 1],
                               typename = GAMENAMES[gametype],
                               sales = int(sales), ncust = ncust,
                               stage = stage,
                               inv = inventory, init_inv = init_inv,
                               price_hist = price_hist,
                               plot_script=script,
                               plot_div=div,
                               js_resources=js_resources,
                               css_resources=css_resources,
                               revenue=totrevenue
                               )
    else:
        return render_template('gameover.html', gameid= gameid, groupname= groupname,
                               has_inv = HASINV[gametype], gametype= gametype,
                               typename=GAMENAMES[gametype],
                               sales = int(sales), ncust = ncust,
                               stage = stage,
                               inv = inventory,
                               price_hist = price_hist,
                               plot_script=script,
                               plot_div=div,
                               js_resources=js_resources,
                               css_resources=css_resources,
                               cumsales= sum(sales_arr), revenue=totrevenue)


#@app.route("/results/<string:gametype>", methods = ['POST'])
def send_results_OLD(gametype):
    global VALUATIONS, GAMETYPES, HASINV

    valuations = VALUATIONS[gametype]
    if not gametype in GAMETYPES:
        return("""<h2> URL not found </h2>""")
    elif HASINV[gametype]:
        init_inv = INITINV
    else:
        init_inv = None
    price_hist = request.form.get("price_hist")
    groupname = request.form.get("groupname")
    gameid = request.form.get("gameid")
    if price_hist:
        currtime = datetime.datetime.now()
        df = gen_results_table(timestamp=str(currtime), gameid= gameid, gametype= gametype, groupid=groupname,
                               price_hist= price_hist, init_inv= init_inv, valuations= valuations)
        try:
            with sql.connect(DATABASE) as con:
                df.to_sql('results',con=con, if_exists='append', index= False)
                con.commit()
            saved = True
        except Exception as e:
            saved = False
            error_msg = str(e)

        if saved:
            currgame_index = GAMETYPES.index(gametype)
            if currgame_index < len(GAMETYPES) - 1:
                nextgame = GAMETYPES[currgame_index+1]
            else:
                nextgame = None

            return render_template("result_confirm.html", tables= [df.to_html(classes='data',header="true")],
                                   nextgame= nextgame, gameid = gameid, groupname= groupname )
        else:
            return("""<h1> Error: results could not be saved</h1>"""+error_msg)
    else:
        return("""Cannot show results: Invalid price input""")



@app.route('/bokeh_test')
def bokeh_test():
    fig1 = draw_results_allgroups(gameid=12345, gametype="inv")
    fig2 = overall_standing(gameid=12345)
    # grab the static resources
    js_resources = INLINE.render_js()
    css_resources = INLINE.render_css()
    # render template
    fig = column(fig1,fig2)
    script, div = components(fig)

    html = render_template('test.html',
                           plot_script=script,
                           plot_div=div,
                           js_resources=js_resources,
                           css_resources=css_resources
                           )
    return (html)



# --------------------------------------------------------


