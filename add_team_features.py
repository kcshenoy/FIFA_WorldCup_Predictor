"""
Adds country population, GDP, and pre-tournament FIFA rank to
team_tournament_features.csv.

Population and GDP: World Bank WDI indicators SP.POP.TOTL and NY.GDP.MKTP.CD,
downloaded via the Datahub CSV mirrors (github.com/datasets/population,
github.com/datasets/gdp), saved in this repo as population.csv / gdp.csv.
Special cases:
England/Scotland/Wales get fixed shares of the UK total
Serbia and Montenegro GDP and Population are combined to match World Cup 2006
North Korea has no published GDP so left NaN

FIFA rank: historical rankings scraped from fifa.com by Dato-Futbol
(github.com/Dato-Futbol/fifa-ranking), saved in this repo as fifa_ranking.csv.
Rank is derived by ordering teams on ranking points within each release,
and each tournament uses the last release before it started.
The 2026 ranks are hardcoded from the official June 11, 2026 release,
as reported by ESPN and FIFA.
Note: The ranking formula changed in August 2018.
"""
import pandas as pd

team_to_country = {
    "Cape Verde":"Cabo Verde",
    "Curaçao":"Curacao",
    "Czech Republic":"Czechia",
    "DR Congo":"Congo, Dem. Rep.",
    "Egypt":"Egypt, Arab Rep.",
    "Iran":"Iran, Islamic Rep.",
    "Ivory Coast":"Cote d'Ivoire",
    "North Korea":"Korea, Dem. People's Rep.",
    "Republic of Ireland":"Ireland",
    "Russia":"Russian Federation",
    "Slovakia":"Slovak Republic",
    "South Korea":"Korea, Rep.",
    "Turkey":"Turkiye",
}

composites = {
    "Serbia and Montenegro":["Serbia","Montenegro"],
}

uk_nations = {
    "England":(0.843,0.860),
    "Scotland":(0.081,0.075),
    "Wales":(0.046,0.034),
    "Northern Ireland":(0.028,0.022),
}

team_to_fifa = {
    "Cape Verde":["Cape Verde Islands","Cabo Verde"],
    "China":["China PR"],
    "Curaçao":["Curaçao","Curacao"],
    "Czech Republic":["Czech Republic","Czechia"],
    "DR Congo":["Congo DR"],
    "Iran":["IR Iran"],
    "Ivory Coast":["Côte d'Ivoire"],
    "North Korea":["Korea DPR"],
    "South Korea":["Korea Republic"],
    "Turkey":["Turkey","Türkiye"],
    "United States":["USA"],
}

tournament_start = {
    "WC-2002":"2002-05-31",
    "WC-2006":"2006-06-09",
    "WC-2010":"2010-06-11",
    "WC-2014":"2014-06-12",
    "WC-2018":"2018-06-14",
    "WC-2022":"2022-11-20",
}

ranks_2026 = {
    "Argentina":1, "Spain":2, "France":3, "England":4, "Portugal":5,
    "Brazil":6, "Morocco":7, "Netherlands":8, "Belgium":9, "Germany":10,
    "Croatia":11, "Colombia":13, "Mexico":14, "Senegal":15, "Uruguay":16,
    "United States":17, "Japan":18, "Switzerland":19, "Iran":20,
    "Turkey":22, "Ecuador":23, "Austria":24, "South Korea":25,
    "Australia":27, "Algeria":28, "Egypt":29, "Canada":30, "Norway":31,
    "Ivory Coast":33, "Panama":34, "Sweden":38, "Czech Republic":40,
    "Paraguay":41, "Scotland":42, "Tunisia":45, "DR Congo":46,
    "Uzbekistan":50, "Qatar":56, "Iraq":57, "South Africa":60,
    "Saudi Arabia":61, "Jordan":63, "Bosnia and Herzegovina":64,
    "Cape Verde":67, "Ghana":73, "Curaçao":82, "Haiti":83,
    "New Zealand":85,
}


def load_series(path,value_name):
    df = pd.read_csv(path)
    df = df.rename(columns={"Country Name":"country","Year":"year","Value":value_name})
    return df[["country","year",value_name]]


def asof_value(series,country,year,value_name):
    rows = series[(series["country"] == country) & (series["year"] < year)]
    if rows.empty:
        return float("nan")
    return rows.loc[rows["year"].idxmax(),value_name]


def lookup(pop,gdp,team,year):
    if team in uk_nations:
        pop_share,gdp_share = uk_nations[team]
        return (asof_value(pop,"United Kingdom",year,"population")*pop_share,
                asof_value(gdp,"United Kingdom",year,"gdp_usd")*gdp_share)
    if team in composites:
        parts = composites[team]
        return (sum(asof_value(pop,c,year,"population") for c in parts),
                sum(asof_value(gdp,c,year,"gdp_usd") for c in parts))
    country = team_to_country.get(team,team)
    return (asof_value(pop,country,year,"population"),
            asof_value(gdp,country,year,"gdp_usd"))


def fifa_rank(tournament_id,team):
    if tournament_id == "WC-2026":
        return ranks_2026[team]
    cutoff = pd.Timestamp(tournament_start[tournament_id])
    release = ranking[ranking["date"] < cutoff]["date"].max()
    snapshot = ranking[ranking["date"] == release]
    names = team_to_fifa.get(team,[team])
    return int(snapshot.loc[snapshot["team"].isin(names),"rank"].iloc[0])


pop = load_series("population.csv","population")
gdp = load_series("gdp.csv","gdp_usd")

ranking = pd.read_csv("fifa_ranking.csv")
ranking = ranking.dropna(subset=["total_points"])
ranking["date"] = pd.to_datetime(ranking["date"])
ranking["rank"] = ranking.groupby("date")["total_points"].rank(ascending=False,method="min").astype(int)

feats = pd.read_csv("team_tournament_features.csv")
vals = [lookup(pop,gdp,t,y) for t,y in zip(feats["team_name"],feats["year"])]
feats["population"] = [v[0] for v in vals]
feats["gdp_usd"] = [v[1] for v in vals]
feats["gdp_per_capita"] = (feats["gdp_usd"]/feats["population"]).round(2)
feats["population"] = feats["population"].round().astype(int)
feats["gdp_usd"] = feats["gdp_usd"].round().astype("Int64")
feats["fifa_rank"] = [fifa_rank(t,n) for t,n in zip(feats["tournament_id"],feats["team_name"])]
feats.to_csv("team_tournament_features.csv",index=False)