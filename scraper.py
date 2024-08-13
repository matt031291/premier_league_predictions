import requests
from bs4 import BeautifulSoup
import pandas as pd

def fetch_data_fixtures(soup):
    table_matches = soup.find('table')#, attrs={'class':'table-main js-tablebanner-t js-tablebanner-ntb'})
    data = []
    rows = table_matches.find_all('tr')
    data=[]
    keep_searching = False
    for row in rows:
        if 'Round' in row.text:
            keep_searching = not keep_searching
        if not keep_searching:
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

def get_teams(match):
    home,away = match.strip(' ').split('-')
    return home,away

def get_gameweek_teams():
    print (1111111)
    URL = "https://www.betexplorer.com/football/england/premier-league/fixtures/"
    #URL = "https://www.betexplorer.com/football/sweden/allsvenskan/fixtures/"
    response = requests.get(URL)
    print (22222222)
    soup = BeautifulSoup(response.text, 'html.parser')
    data = fetch_data_fixtures(soup)
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
    return {ordered_list[i].strip():20-i-L for i in range(len(ordered_list))}



def get_result_points_home(result_str):
    home,away = result_str.split(':')
    if int(home)==int(away):
        return 1
    elif int(home)>int(away):
        return 3
    elif int(home)< int(away):
        return 0

def get_result_points_away(result_str):
    home,away = result_str.split(':')
    if int(home)==int(away):
        return 1
    elif int(home)<int(away):
        return 3
    elif int(home)> int(away):
        return 0



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