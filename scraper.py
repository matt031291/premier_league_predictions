import requests
from bs4 import BeautifulSoup
import pandas as pd
import dateparser
import logging

logger = logging.getLogger('golden_picks.scraper')

TEAM_MAPS = {"Burnley":"BUR","Sunderland":"SUN","Leeds": "LEE","Leicester": "LEI", "ManchesterCity":"MCI","Liverpool":"LIV","WestHam":"WHU","Chelsea":"CHE","Ipswich":"IPS","Arsenal":"ARS","Brentford":"BRE","CrystalPalace":"CRY","Southampton":"SOU","Tottenham":"TOT","Wolves":"WOL","AstonVilla":"AVL","Brighton":"BHA","Fulham":"FUL","Bournemouth":"BOU","Newcastle":"NEW","ManchesterUtd":"MUN","Everton":"EVE","Nottingham":"NFO"}

def fetch_data_fixtures(soup, round):
    table_matches = soup.find('table')
    if table_matches is None:
        logger.error("No table found on fixtures page")
        return pd.DataFrame(columns=['Date','Match','1','X','2'])
    data = []
    rows = table_matches.find_all('tr')
    keep_searching = False
    start_searching = False
    if round is None:
        round = 1
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
            for element in cols:
                try:
                    if 'data-odd' in element.attrs:
                        pass
                    else:
                        utils.append(element.span.span.span['data-odd'])
                except:
                    utils.append(element.text)
            if len(utils) == 10:
                data.append(utils)
    df = pd.DataFrame(data,columns=["1","X","2","Date","Match","-","-","-","-","-"])
    return df[['Date','Match','1','X','2']]


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
    try:
        URL = "https://www.betexplorer.com/football/england/premier-league/fixtures/"
        response = requests.get(URL, timeout=15)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')
        data = fetch_data_fixtures(soup, round)

        if data.empty:
            logger.warning(f"No fixture data for round {round}")
            return None

        data['Date'] = data['Date'].apply(process_date)
        first_game = data['Date'].min() - pd.Timedelta(minutes=90)
        return first_game
    except Exception as e:
        logger.error(f"get_next_start_time failed for round {round}: {e}")
        return None

def get_gameweek_teams(round):
    try:
        URL = "https://www.betexplorer.com/football/england/premier-league/fixtures/"
        response = requests.get(URL, timeout=15)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')
        data = fetch_data_fixtures(soup, round)

        if data.empty:
            logger.error(f"No fixture data for round {round} — returning empty")
            return {}, {}, None, None

        data['Date'] = data['Date'].apply(process_date)
        first_game = data['Date'].min() - pd.Timedelta(minutes=90)
        last_game = data['Date'].max() + pd.Timedelta(minutes=240)

        data[['home1','away1']]  = data['Match'].apply(get_teams).apply(pd.Series)
        data['home'] = data['home1'] + '_' + data['away1'] +'_H'
        data['away'] = data['away1'] + '_' + data['home1'] +'_A'
        data['home']=data['home'].str.replace(' ','')
        data['away']=data['away'].str.replace(' ','')

        odds = {}
        ex_points = {}
        for _,row in data.iterrows():
            win = 1/float(row['1'])
            draw = 1/ float(row['X'])
            lose = 1/float(row['2'])
            total = (win + draw+lose)
            win2 = win/total
            draw2 = draw/total
            lose2 = lose/total

            odds[row['home']]=float(row['1'])
            odds[row['away']]= float(row['2'])

            ex_points[row['home']] = 3*win2 + draw2
            ex_points[row['away']] = 3*lose2 + draw2

        sorted_odds= dict(sorted(odds.items(), key=lambda item: float(item[1])))
        ordered_list = list(sorted_odds.keys())
        L =  (20-len(ordered_list))/2
        logger.info(f"Scraped round {round}: {len(ordered_list)} teams")
        return {ordered_list[i].strip():20-i-L for i in range(len(ordered_list))},ex_points, first_game, last_game
    except Exception as e:
        logger.error(f"get_gameweek_teams failed for round {round}: {e}")
        return {}, {}, None, None


def get_result_points_home(result_str):
    home,away = result_str.split(':')
    return int(home)- int(away)

def get_result_points_away(result_str):
    home,away = result_str.split(':')
    return int(away) - int(home)


def fetch_data_results(soup):
    table_matches = soup.find('table')
    if table_matches is None:
        logger.error("No table found on results page")
        return pd.DataFrame(columns=["Match","result","odds","date"])
    data = []
    rows = table_matches.find_all('tr')
    for row in rows:
        utils = []
        cols = row.find_all('td')
        utils = [button['data-odd'] for button in row.find_all('button')]
        for element in cols:
            try:
                if 'data-odd' in element.attrs:
                    pass
                else:
                    utils.append(element.span.span.span['data-odd'])
            except:
                utils.append(element.text)

        if len(utils) == 4:
            data.append(utils)

    df = pd.DataFrame(data,columns=["Match","result","odds","date"])
    return df

def get_results():
    try:
        URL = "https://www.betexplorer.com/football/england/premier-league/results/"
        response = requests.get(URL, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        data = fetch_data_results(soup)
        if data.empty:
            logger.warning("No results data found")
            return {}

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
    except Exception as e:
        logger.error(f"get_results failed: {e}")
        return {}


def fetch_data_scores(soup, round):
    table_matches = soup.find('table')
    if table_matches is None:
        logger.error("No table found on results page for scores")
        return pd.DataFrame(columns=["Match","result","odds","date"])
    data = []
    rows = table_matches.find_all('tr')
    total_rounds = 0
    for row in rows:
        if 'Round' in row.text and str(round -1)+'.' in row.text:
            total_rounds += 1
            if total_rounds == 1:
                break
        utils = []
        cols = row.find_all('td')
        utils = [button['data-odd'] for button in row.find_all('button')]
        for element in cols:
            try:
                if 'data-odd' in element.attrs:
                    pass
                else:
                    utils.append(element.span.span.span['data-odd'])
            except:
                utils.append(element.text)

        if len(utils) == 4:
            data.append(utils)

    df = pd.DataFrame(data,columns=["Match","result","odds","date"])
    return df

def get_round_scores(round):
    try:
        URL = "https://www.betexplorer.com/football/england/premier-league/results/"
        response = requests.get(URL, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        data = fetch_data_scores(soup, round)
        if data.empty:
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
    except Exception as e:
        logger.error(f"get_round_scores failed for round {round}: {e}")
        return []
