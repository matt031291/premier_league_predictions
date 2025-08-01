import requests
from bs4 import BeautifulSoup
import pandas as pd
import dateparser
TEAM_MAPS = {"Burnley":"BUR","Sunderland":"SUN","Leeds": "LEE","Leicester": "LEI", "ManchesterCity":"MCI","Liverpool":"LIV","WestHam":"WHU","Chelsea":"CHE","Ipswich":"IPS","Arsenal":"ARS","Brentford":"BRE","CrystalPalace":"CRY","Southampton":"SOU","Tottenham":"TOT","Wolves":"Wol","AstonVilla":"AVL","Brighton":"BHA","Fulham":"FUL","Bournemouth":"BOU","Newcastle":"NEW","ManchesterUtd":"MUN","Everton":"EVE","Nottingham":"NFO"}

def fetch_data_fixtures(soup, round ):
    table_matches = soup.find('table')#, attrs={'class':'table-main js-tablebanner-t js-tablebanner-ntb'})
    data = []
    rows = table_matches.find_all('tr')
    data=[]
    keep_searching = False
    start_searching = False
    if round is None:
        round = 1 #This needs to be changed for testing to most recent round
    for row in rows:
        if 'Round' in row.text and str(round)+'.' in row.text:
            start_searching = True
        if start_searching:
            if 'Round' in row.text and str(round+1)+'.' in row.text:
                df = pd.DataFrame(data,columns=["1","X","2","Date","Match","-","-","-","-","-"])
                return df[['Date','Match','1','X','2']]

            utils = []
            cols = row.find_all('td')
            utils = [button['data-odd'] for button in row.find_all('button')]
            # Extract fixture name
            for element in cols:
                try:
                    # Store the odds that win and didnt win
                    if 'data-odd' in element.attrs:
                        pass
                    else:
                        utils.append(element.span.span.span['data-odd'])
                except:
                    # Store the text
                    utils.append(element.text)
            if len(utils) == 10:
                data.append(utils)
    df = pd.DataFrame(data,columns=["1","X","2","Date","Match","-","-","-","-","-"])
    return df[['Date','Match','1','X','2']]


# Function to handle both cases
def process_date(date_str):
    dt = dateparser.parse(
        date_str,
        settings={
            'DATE_ORDER': 'DMY',
            'PREFER_DATES_FROM': 'future',
        }
    )
    if dt is None:
        return None    
    return pd.Timestamp(dt)

def get_teams(match):
    home,away = match.strip(' ').split('-')
    return home,away

def get_next_start_time(round):
    round = round
    URL = "https://www.betexplorer.com/football/england/premier-league/fixtures/"
    #URL = "https://www.betexplorer.com/football/sweden/allsvenskan/fixtures/"
    response = requests.get(URL)

    soup = BeautifulSoup(response.text, 'html.parser')
    data = fetch_data_fixtures(soup,round)

    data['Date'] = data['Date'].apply(process_date)
    first_game = data['Date'].min() - pd.Timedelta(minutes=90)
    return first_game

def get_gameweek_teams(round):
    print (1111111)
    round = round
    URL = "https://www.betexplorer.com/football/england/premier-league/fixtures/"
    #URL = "https://www.betexplorer.com/football/sweden/allsvenskan/fixtures/"
    response = requests.get(URL)

    soup = BeautifulSoup(response.text, 'html.parser')
    data = fetch_data_fixtures(soup,round)

    data['Date'] = data['Date'].apply(process_date)
    first_game = data['Date'].min() - pd.Timedelta(minutes=90)
    last_game = data['Date'].max() + pd.Timedelta(minutes=240)


    data[['home1','away1']]  = data['Match'].apply(get_teams).apply(pd.Series)
    data['home'] = data['home1'] + '_' + data['away1'] +'_H'
    data['away'] = data['away1'] + '_' + data['home1'] +'_A'
    data['home']=data['home'].str.replace(' ','')
    data['away']=data['away'].str.replace(' ','')

    odds = {}
    for _,row in data.iterrows():
        odds[row['home']]=float(row['1'])
        odds[row['away']]= float(row['2'])


    sorted_odds= dict(sorted(odds.items(), key=lambda item: float(item[1])))
    ordered_list = list(sorted_odds.keys())
    L =  (20-len(ordered_list))/2
    return {ordered_list[i].strip():20-i-L for i in range(len(ordered_list))}, first_game, last_game



def get_result_points_home(result_str):
    home,away = result_str.split(':')
    return int(home)- int(away)

def get_result_points_away(result_str):
    home,away = result_str.split(':')
    return int(away) - int(home)



def fetch_data_results(soup):
    table_matches = soup.find('table')#, attrs={'class':'table-main js-tablebanner-t js-tablebanner-ntb'})
    data = []
    rows = table_matches.find_all('tr')
    data=[]
    for row in rows:
        utils = []
        cols = row.find_all('td')
        utils = [button['data-odd'] for button in row.find_all('button')]
        # Extract fixture name
        for element in cols:
            try:
                # Store the odds that win and didnt win
                if 'data-odd' in element.attrs:
                    pass
                else:
                    utils.append(element.span.span.span['data-odd'])
            except:
                # Store the text
                utils.append(element.text)

        if len(utils) == 4:
            data.append(utils)


    df = pd.DataFrame(data,columns=["Match","result","odds","date"])
    return df

def get_results():
    URL = "https://www.betexplorer.com/football/england/premier-league/results/"
    response = requests.get(URL)
    soup = BeautifulSoup(response.text, 'html.parser')

    data = fetch_data_results(soup)
    data[['home1','away1']]  = data['Match'].apply(get_teams).apply(pd.Series)
    data['home'] = data['home1'] + '_' + data['away1'] +'_H'
    data['away'] = data['away1'] + '_' + data['home1'] +'_A'
    data['home']=data['home'].str.replace(' ','')
    data['away']=data['away'].str.replace(' ','')

    data['points_home']=data['result'].apply(get_result_points_home).apply(pd.Series)
    data['points_away']=data['result'].apply(get_result_points_away).apply(pd.Series)
    points = {}
    for _,row in data.iterrows():
        points[row['home']]=int(row['points_home'])
        points[row['away']]= float(row['points_away'])

    return points


def fetch_data_scores(soup, round):
    table_matches = soup.find('table')#, attrs={'class':'table-main js-tablebanner-t js-tablebanner-ntb'})
    data = []
    rows = table_matches.find_all('tr')
    data=[]
    total_rounds = 0
    for row in rows:
        if 'Round' in row.text and str(round -1)+'.' in row.text:
            total_rounds += 1
            if total_rounds == 1:
                break
        utils = []
        cols = row.find_all('td')
        utils = [button['data-odd'] for button in row.find_all('button')]
        # Extract fixture name
        for element in cols:
            try:
                # Store the odds that win and didnt win
                if 'data-odd' in element.attrs:
                    pass
                else:
                    utils.append(element.span.span.span['data-odd'])
            except:
                # Store the text
                utils.append(element.text)

        if len(utils) == 4:
            data.append(utils)


    df = pd.DataFrame(data,columns=["Match","result","odds","date"])
    return df

def get_round_scores(round):
    URL = "https://www.betexplorer.com/football/england/premier-league/results/"
    response = requests.get(URL)
    soup = BeautifulSoup(response.text, 'html.parser')
    round = round
    data = fetch_data_scores(soup, round)
    if len(data) == 0:
        return []
    data[['home1','away1']]  = data['Match'].apply(get_teams).apply(pd.Series)
    data['home'] = data['home1'] + '_' + data['away1'] +'_H'
    data['away'] = data['away1'] + '_' + data['home1'] +'_A'
    data['home']=data['home'].str.replace(' ','')
    data['away']=data['away'].str.replace(' ','')


    scores = []
    for _,row in data.iterrows():
        h,a = row.result.split(':')
        try:
            score = {"team1": TEAM_MAPS[row['home1'].replace(' ','')], "team2": TEAM_MAPS[row['away1'].replace(' ','')], "score1": int(h), "score2": int(a)}
        except KeyError:
            score = {"team1": row['home1'].replace(' ',''), "team2": row['away1'].replace(' ',''), "score1": int(h), "score2": int(a)}

        scores += [score]
    return scores
