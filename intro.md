
I have been studing the greatest market wizards for latest 2 years. I would like to construct a program, method that will help me achieve the performances of the market wizard. I would like to use AI to help me with organizing the info etc.
Based on my observation: AI lacks still the knowledge to by himself manage a portfolio. It also lacks the understanding of a trend, set up, entry, risk management, low risk entry that is often needed to manage a portfolio without having big drawdowns.

Therefore, my idea is: instead of allowing AI to actually run and mange a portfolio, better to alert and present the human operator(myslef) with up to date, unbiased information that will allow me to pickup the winners of the market cycles.
The methods that "select", "filter" a potential market leader are based on CANSLIM, William ONeill, Stan Weinstein, Minervini methods.

step 1: Market, sector, industry - this module in in under development in another folder
step 2: Filters - subject of this module
step 3: Buy rules: set up, entry  - not subject of current development
step 4: Sell rules etc - not subject of current development

0) "Universe list": tradingview_univrese.csv or ticker_choice = 0 in the /home/imagda/_invest2024/python/downloadData_v1 project. All historical data are downloaded in: /home/imagda/_invest2024/python/downloadData_v1/data/market_data and /home/imagda/_invest2024/python/downloadData_v1/data/market_data_batch . The list conatins about 4,000 stocks.

1) 1ST CAT FILTERS: Create Leaders' Lists
Filters: At the present  we only have  3 filters. In the future new filters may be added. 

Leaders's List: Running filters over the "Universe List" will create 3 leaders list. Some of the stocks will appear in multiple lists at same time. Each of these filters will create 1 filtered output/filter. In the future I would be able to perform operations (intersection, union, threshold criteria filtering); or combined (unify all 3 into 1, remove duplicates)

a) Minervini Filter
b) CANSLIM - but only focus on CA**I* - I think they are the only one that can be filtered by using financial data
c) SCOOTER score

A ticker that is on the leader list: it doesnt mean it has to be bought straightaway. A good trade requires also other ingredients: low risk entry point etc..

2) 2ND CAT FILTERS: Create Focus's List

Many of the STOCKS ON "Leaders' Lists" may be tranding for months, and may be extended, starting a downtrend vs pullback etc. The filters appled at this level will ensure certain threshold are respected, can be filtered by. For this we need to calculate  and be able to filter after:

a) ATR extensions  vs 21 EMA, 40 SMA: https://www.tradingview.com/v/60GMm8mE/
b) ADR
c) stage clasiffication: weinstein + detailes (1-4, abc stages) 
d) RTI: https://www.tradingview.com/v/yaIeno72/
e) we may add other crietria/filters in the future

How to construct this:

- dashboard format: https://www.youtube.com/watch?v=nlRNLtpCQnE. See attached image in folder: dashboard_format.png

The project is designed for screening and not backtesting purposes. I have constructed in the past part of modules that were mentioned in the project:
 
 - scooter implementation:  /home/imagda/_invest2024/python/yf-gics; /home/imagda/_invest2024/python/test_scooter 
 - minervini implementation:  /home/imagda/_invest2024/python/lkm_rs
 - collections of screeners: /home/imagda/_invest2024/python/metaData_v1 in screeners 
 
 
 



