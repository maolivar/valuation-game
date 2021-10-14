# Valuation Game

## Instructions to play valuation-game

`valuation-game` is a simulation exercise useful for introducing students to price optimization and revenue management. The game is based on the game developed by
Kalyan Talluri (see [paper](https://pubsonline.informs.org/doi/pdf/10.1287/ited.1090.0029) ).

The alpha version of the game is currently deployed in [Heroku](valuation-game.herokuapp.com).

Basic instructions to play the game:

- Enter the link: https://valuation-game.herokuapp.com
- The full game consists on three simulations, each simulation lasts for 5 weeks

Simulation 1: base scenario:
- A random number of customers (between 10-20) arrive each day. Each customer has a valuation for the product, which is randomly picked from a distribution of 
valuations declared by real people. They range from $100,000 to $5,000,000 Chilean pesos.
- Every week, the player chooses a price. All customers with valuations higher then the price purchase the product.
- After 5 weeks, total revenues are calculated and the player is asked to submit results, which are stored in the local database.
- Player can click to start the next simulation.

Simulation 2: inventory
- Similar to simulation 1 but now there is a limited amount of inventory to sell during the 5 weeks. The initial inventory is set to 40 units.
- As before, player can choose prices every week.
- Player may run out of inventory, in which case he/she cannot sell the product in the incoming weeks.
- **Right now, player continues to set prices even after running out of inventory** . This is a possible fix for future versions.
- As before, player stores results at the end of simulation and may choose to play the next simulation.

Simulation 3: inventory and price discrimination
- Similar to simulation 2 but now customer valuations vary across weeks. During the first 4 weeks, customers have a lower valuation, and the last week they have a higher valuation.
- In the current setup, low valuations corresponds to the bottom 80% of the valuation distribution, and high valuation from the top 20%.
- Rest of the game is identifical.

To view the stored results so far, can use the path extension /get_results on the URL.

Future improvements:
- Add an administration panel to view results and change game parameters.
- Implement a game password and player registration panel.
- Improve CSS design.
- Other suggestions are welcome (but keep it simple).


## Development notes

valuation-game is developed in Python using Flask framework to implement the web-app. It uses a local Sqlite database to store game results. It is currently under development, so any suggestions for improvement are very much welcomed!

