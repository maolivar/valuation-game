# Valuation Game

## Instructions to play valuation-game

`valuation-game` is a simulation exercise useful for introducing students to price optimization and revenue management. The game is based on the exercise developed by Kalyan Talluri (see [paper](https://pubsonline.informs.org/doi/pdf/10.1287/ited.1090.0029) ).

The alpha version of the game is currently deployed in [Heroku](valuation-game.herokuapp.com).

### Basic instructions to play the game:

Create or enter existing game:

- Go to the admin login page: https://valuation-game.herokuapp.com/adminLogin
- Choose to create a new game or enter existing game. When a new game is created, a game password is created automatically.
- The administrator dashboard will be displayed (with empty charts for a newly created game).

Register players:

- Player login: https://valuation-game.herokuapp.com/login
- Enter game password provided by admin. Create a group name (choose a short name).
- Start the game in the first simulation.

### Game description

The full game consists on three simulations, each simulation lasts for 5 periods, where each period corresponds to a week.

*Simulation 1: base scenario:*
- A random number of customers (between 10-20) arrive each week. Each customer has a valuation for the product, which is randomly picked from a distribution of 
valuations declared by real people that where asked to provide the willingness to pay for a cruise package in the coast of Rio de Janeiro. They range from $100,000 to $5,000,000 Chilean pesos.
- Every week, the player chooses a price. All customers with valuations higher than the price purchase the product.
- After 5 weeks, total revenues are calculated and the player is asked to submit results, which are stored in the local database.
- Player can click to start the next simulation.

*Simulation 2: limited inventory*
- Similar to simulation 1 but now there is a limited amount of inventory to sell during the 5 weeks. The initial inventory is set to 40 units.
- As before, player can choose prices every week.
- Player may run out of inventory, in which case he/she cannot sell the product in the incoming weeks.
- **Right now, player continues to set prices even after running out of inventory** . This is a possible fix for future versions.
- As before, player stores results at the end of simulation and may choose to play the next simulation.

*Simulation 3: limited inventory and price discrimination*
- Similar to simulation 2 but now customer valuations vary across weeks. During the first 4 weeks, customers have a lower valuation, and the last week they have a higher valuation.
- In the current setup, low valuations corresponds to the bottom 80% of the valuation distribution, and high valuation from the top 20%.
- Rest of the game is identifical.

## Viewing results

At the end of each round, players have to submit their results.

The results of all groups can be viewed in the admin Dashboard. The admin can change the simulation to be viewed:
- `base` = Simulation 1
- `inv` = Simulation 2
- `disc` = Simulation 3

If  simulation has no results, an empty plot is shown.

To view the stored results so far in the database, the instructor can use the path extension `/get_results` on the URL of the game.

Future improvements:
- Add login for administrators
- Dashboard to manage existing games
- Other suggestions are welcomed.


## Development notes

`valuation-game` is developed in Python using Flask framework to implement the web-app. 
It uses a local SQLite database to store game results. 
All the plots are generated using [Bokeh](https://docs.bokeh.org/en/latest/index.html) framework.
It is currently under development, so any suggestions for improvement are very much welcomed!

