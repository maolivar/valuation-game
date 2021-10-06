# This is a sample Python script.

# Valuation game, v1.0
# By Marcelo Olivares
# First version: 10/04/2021

import random
import base64
import numpy as np
from io import BytesIO

from flask import Flask, render_template
from flask import request
from matplotlib.figure import Figure



app = Flask(__name__)

NPERIODS = 3

valdist = list(range(5,200))
valuations = []
for n in range(NPERIODS):
    ncust = random.randint(10,20)
    valuations.append(random.choices(valdist, k = ncust))
print(valuations)

@app.route("/")
def index():
    global NPERIODS
    price = request.args.get("price")
    stage = request.args.get("stage")
    price_hist = request.args.get("price_hist")
    sales_hist = request.args.get("sales_hist")
    if price and stage:
        stagenum = int(stage)
        sales = get_sales(float(price),valuations[stagenum-1])
        price_hist = price_hist+price+","
        sales_hist = sales_hist+sales+","
        stagenum = stagenum + 1
    else:
        price_hist=""
        sales_hist=""
        stagenum = 1

    stage = str(stagenum)

    if stagenum>1:
        fig = draw_graph(price_hist)
        # Save it to a temporary buffer.
        buf = BytesIO()
        fig.savefig(buf, format="png")
        # Embed the result in the html output.
        data = base64.b64encode(buf.getbuffer()).decode("ascii")

    if stagenum == 1:
        return render_template('welcome.html', PageTitle= "Welcome",
                               stage = stage,
                               nperiods = str(NPERIODS))
    elif stagenum <= NPERIODS:
        return render_template('inplay.html',
                               sales = int(sales), stage=stage, data_plot = data,
                               price_hist = price_hist, sales_hist = sales_hist)
    else:
        return render_template('gameover.html', sales = int(sales), data_plot = data,
                               revenue="TO BE CALCULATED")
        # return (
        #     head_text + "<br>" +
        #     "Stage:" + str(stagenum) +
        #     """<form action="" method="get">
        #             <input type="hidden" value="%s" name="stage" /> """%str(stagenum) +
        #     """     <input type="hidden" value="%s" name="sales_hist" /> """%sales_hist +
        #     """     <input type="hidden" value="%s" name="price_hist" /> """%price_hist +
        #     """     Choose your price: <input type="text" name="price">
        #             <input type="submit" value="Submit price">
        #         </form>"""+
        #     fig_text
        # )

# THIS IS FOR TESTING
@app.route("/hello")
def hello():
    # Generate the figure **without using pyplot**.
    y = [3,5,6,2,4]
    x = [1,2,3,4,5]
    fig = Figure()
    ax = fig.subplots()
    ax.plot(x,y)
    # Save it to a temporary buffer.
    buf = BytesIO()
    fig.savefig(buf, format="png")
    # Embed the result in the html output.
    data = base64.b64encode(buf.getbuffer()).decode("ascii")
    return f"<img src='data:image/png;base64,{data}'/>"


def get_sales(pricenum,values):
    """Calculate sales for the submitted (numeric) price"""
    sales = 0
    for i in range(len(values)):
        sales = sales + (values[i]>=pricenum)
    return str(sales)

def get_sales_hist(price_list):
    global valuations
    tperiod = len(price_list)
    sales_list = []
    ncust_list = []
    for t in range(tperiod):
        sales_list.append(int(get_sales(price_list[t],valuations[t])))
        ncust_list.append(len(valuations[t]))
    sales_arr = np.array(sales_list)
    ncust_arr = np.array(ncust_list)
    return sales_arr, ncust_arr


def draw_graph(price_hist):
    global NPERIODS
    price_list=[int(x) for x in price_hist.split(',') if x.strip().isdigit()]
    price_arr = np.array(price_list)
    x = list(range(1,len(price_list)+1))
    fig = Figure()
   # ax = fig.subplots()
    ax = fig.add_subplot(211)
 #   ax.set_xlabel('week')
    ax.set_ylabel('price')
    ax.set_xlim(xmin=0, xmax=NPERIODS+1)
    ax.set_xticks(list(range(1,NPERIODS+1)))
    ax.set_title('Price history')
    ax.plot(x, price_list)
    ax.scatter(x, price_list)

    (sales_arr,ncust_arr) = get_sales_hist(price_list)
    lostsales_arr = ncust_arr - sales_arr
    ax2 = fig.add_subplot(212)
    ax2.bar(x, sales_arr, label='Sales')
    ax2.bar(x, lostsales_arr, bottom=sales_arr, label="No purchase")
    ax2.set_xlabel('week')
    ax2.set_ylabel('customers')
    ax2.set_xlim(xmin=0, xmax=NPERIODS+1)
    ax2.set_xticks(list(range(1,NPERIODS+1)))
    ax2.set_title('Sales history')

    return fig

# Following line is to run locally
#if __name__ == "__main__":
#    app.run(host="127.0.0.1", port=8080, debug=True)

if __name__ == "__main__":
    app.run(debug=True)