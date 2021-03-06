import sys
import calendar 

import numpy as np
import pandas as pd
import datetime as dt
from scipy.stats import entropy
import statsmodels.api as sm

from sklearn.gaussian_process import GaussianProcessRegressor
from sklearn.gaussian_process.kernels import RBF, ConstantKernel as C

from collections import Counter

FRAMES = ['Economic',
         'Capacity_and_resources',
         'Morality',
         'Fairness_and_equality',
         'Legality_jurisdiction',
         'Policy_prescription',
         'Crime_and_punishment',
         'Security_and_defense',
         'Health_and_safety',
         'Quality_of_life',
         'Cultural_identity',
         'Public_sentiment',
         'Political',
         'External_regulation',
         'Other']

FRAMES_COMBO = ['Economic',
         'Capacity_and_resources',
         'Morality',
         'Fairness_and_equality',
         'Legality_jurisdiction',
         'Policy_prescription',
         'Crime_and_punishment',
         'Security_and_defense',
         'Health_and_safety',
         'Quality_of_life',
         'Cultural_identity',
         'Public_sentiment',
         'Political',
         'External_regulation',
         'Other']

#FRAMES_COMBO = ['Economic_and_Capacity',
#         'Morality_and_Fairness',
#         'Legality_jurisdiction',
#         'Crime_and_Security',
#         'Health_and_safety',
#         'Quality_of_life',
#         'Cultural_identity',
#         'Public_sentiment',
#         'Political_and_Policy',
#         'External_regulation',
#         'Other']

def read_article_data(data_file, first_year, last_year, rename_frames=False, exclude_irrelevant=True, flip_tone=False, use_body=False):
    """
    Read in tone predictions for an issue and return a pandas DataFrame
    :param data_file (.csv file): file containing the predictions
    :param first_year (int): Exclude all rows prior to this year
    :return: pandas DataFrame
    """

    # read the data into a pandas data frame
    data = pd.read_csv(data_file, header=0, index_col=0)

    # exclude articles marked as "irrelevant" and those from before 1980
    if exclude_irrelevant:
        data = data.loc[(data['Irrelevant']==0) & (data['Year'] >= first_year) & (data['Year'] <= last_year)]
    else:
        data = data.loc[(data['Year'] >= first_year) & (data['Year'] <= last_year)]        

    #if flip_tone:
    #    pro = data['Pro'].values.copy()
    #    anti = data['Anti'].values.copy()
    #    data['Anti'] = pro
    #    data['Pro'] = anti

    # combine year, month, day into a single date variable
    data['date'] = data.apply(lambda row: pd.Timestamp(dt.date(row['Year'], row['Month'], row['Day'])), axis=1)

    if rename_frames:
        columns = list(data.columns)
        for f_i, f in enumerate(FRAMES):
            if use_body:
                col_index = columns.index('b' + str(f_i))
            else:
                col_index = columns.index('p' + str(f_i))
            columns[col_index] = f
        data.columns = columns
        
    return data


def bundle_frames(data):
    data['Crime_and_Security'] = data['Crime_and_punishment'] + data['Security_and_defense']
    data['Morality_and_Fairness'] = data['Morality'] + data['Fairness_and_equality']
    data['Economic_and_Capacity'] = data['Economic'] + data['Capacity_and_resources']
    data['Political_and_Policy'] = data['Political'] + data['Policy_prescription']
    return data


def convert_dates(df, first_year):
    df['year'] = [d.year for d in df['date']]
    df['month'] = [d.month for d in df['date']]
    df['day'] = [d.day for d in df['date']]
    df['quarter'] = [d.quarter for d in df['date']]
    df['p_month'] = [(d.year - first_year)*12 + (d.month - 1) for d in df['date']]
    df['p_quarter'] = [(d.year - first_year)*4 + (d.quarter - 1) for d in df['date']]
    df['p_year'] = [(d.year - first_year) for d in df['date']]
    df['p_day'] = dates_to_days(df['date'], first_year)
    df['p_week'] = [(d.year - first_year) * 52 + (d.weekofyear - 1) for d in df['date']]
    return df



def get_f_dates(data, first_year, group_by):
    # create a grouping of articles by year/quarter
    if group_by == 'day':
        data['f_date'] = 0.0
        for i in data.index:
            year = data.loc[i, 'year']
            if calendar.isleap(year):
                data.loc[i, 'f_date'] = data.loc[i, 'year'] + (data.loc[i, 'date'].dayofyear-1) / 366.0
            else:
                data.loc[i, 'f_date'] = data.loc[i, 'year'] + (data.loc[i, 'date'].dayofyear-1) / 365.0
    elif group_by == 'week':
        data['f_date'] = 0.0
        for i in data.index:
            data.loc[i, 'f_date'] = data.loc[i, 'year'] + (data.loc[i, 'date'].weekofyear-1) / 52.0
    elif group_by == 'month':
        data['f_date'] = data['year'] + (data['month'] - 1) / 12.0
        data['period'] = data['p_month']
    elif group_by == 'quarter':
        data['f_date'] = data['year'] + (data['quarter'] - 1) / 4.0
        data['period'] = data['p_quarter']
    elif group_by == 'year':
        data['f_date'] = data['year']
        data['period'] = data['p_year']
    else:
        sys.exit('group_by not recognized')
    data['f_date_0'] = data['f_date'] - first_year
    return data


def group_article_data(data, group_by, first_year, group_tone=False, group_frames=False, group_directness=False):
    """
    Group the data in a DataFrame by either month or quarter
    :param data (DataFrame): the data frame to group
    :param group_by (str): either 'month' or 'quarter'
    :return A new DataFrame grouped accordingly
    """

    # create a dummy variable = 1 for all articles
    data['stories'] = 1    

    data = get_f_dates(data, first_year, group_by)        

    if group_tone and group_frames:
        for c in FRAMES_COMBO:
            data[c + '_pro'] = data[c] * data['Pro']
            data[c + '_anti'] = data[c] * data['Anti']
      
    if group_by == 'quarter':
        groups = data.groupby('p_quarter')
    elif group_by == 'month':
        groups = data.groupby('p_month')
    elif group_by == 'year':
        groups = data.groupby('p_year')
    elif group_by == 'week':
        groups = data.groupby('p_week')
    else:
        sys.exit('group_by not recognized')
      
    # create a new dataframe "grouped", which is what we will work with
    grouped = pd.DataFrame()
    grouped['f_date'] = groups.aggregate(np.mean)['f_date']
    grouped['f_date_0'] = groups.aggregate(np.mean)['f_date_0']

    # add up the total number of articles per quarter and store in grouped
    grouped['stories'] = groups.aggregate(np.sum)['stories']

    if group_tone:
        grouped['Pro'] = groups.aggregate(np.sum)['Pro']
        grouped['Neutral'] = groups.aggregate(np.sum)['Neutral']
        grouped['Anti'] = groups.aggregate(np.sum)['Anti']
    grouped['tone'] = grouped['Pro'] - grouped['Anti']

    if group_directness:
        grouped['Explicit'] = groups.aggregate(np.sum)['Explicit']
        grouped['Implicit'] = groups.aggregate(np.sum)['Implicit']

    if group_frames:
        for c in FRAMES_COMBO:
            grouped[c] = groups.aggregate(np.sum)[c]

    if group_frames and group_tone:
        for c in FRAMES_COMBO:
            grouped[c + '_pro'] = groups.aggregate(np.sum)[c + '_pro']
            grouped[c + '_anti'] = groups.aggregate(np.sum)[c + '_anti']

    log_stories = np.log(grouped['stories'].values)
    grouped['logStories'] = log_stories - float(np.mean(log_stories))

    return grouped


def compute_entropy(df):
    for i, index in enumerate(df.index):
        row = df.loc[index]
        frame_vals = np.array([row[f] for f in FRAMES_COMBO])    
        frame_vals = frame_vals / np.sum(frame_vals)
        df.loc[index, 'entropy'] = entropy(frame_vals)
    return df


def compute_truncated_entropy(df):
    for i, index in enumerate(df.index):
        row = df.loc[index]
        frame_vals = list(np.array([row[f] for f in FRAMES_COMBO]).tolist())
        frame_vals.sort()
        frame_vals.reverse()
        frame_vals = np.array(frame_vals) / np.sum(frame_vals)
        for j in range(2, 15):
            df.loc[index, 'entropy_' + str(j)] = entropy(frame_vals[:j])
    return df


def compute_signed_entropy(df):
    for i, index in enumerate(df.index):
        row = df.loc[index]
        frame_vals = np.array([row[f + '_pro'] for f in FRAMES_COMBO]) 
        frame_vals = frame_vals / np.sum(frame_vals)
        df.loc[index, 'entropy_pro'] = entropy(frame_vals)

        frame_vals = np.array([row[f + '_anti'] for f in FRAMES_COMBO]) 
        frame_vals = frame_vals / np.sum(frame_vals)
        df.loc[index, 'entropy_anti'] = entropy(frame_vals)
    return df


def compute_dominance(df, threshold=0):
    df['dom'] = 0
    df['d_pro'] = 0
    df['d_anti'] = 0
    df['top_pro'] = 0
    df['top_anti'] = 0
    df['top_pro_counts'] = 0
    df['top_anti_counts'] = 0
    df['top_pro_percent'] = 0.0
    df['top_anti_percent'] = 0.0
    df['d_pro_percent'] = 0.0
    df['d_anti_percent'] = 0.0
    for i, index in enumerate(df.index):
        row = df.loc[index]
        stories = row['stories']
        frame_counts = list((np.array([row[f] for f in FRAMES_COMBO])).tolist())
        order = np.argsort(frame_counts)
        frame_counts.sort()
        #df.loc[index, 'd1m2'] = frame_counts[-1] - frame_counts[-2]
        #df.loc[index, 'd1p2'] = frame_counts[-1] + frame_counts[-2]

        frame_counts_pro = list((np.array([row[f + '_pro'] for f in FRAMES_COMBO])).tolist())
        
        order = np.argsort(frame_counts_pro)
        frame_counts_pro.sort()
        df.loc[index, 'd_pro'] = frame_counts_pro[-1] - frame_counts_pro[-2]
        df.loc[index, 'd_pro_percent'] = (frame_counts_pro[-1] - frame_counts_pro[-2]) / float(np.sum(frame_counts))
        df.loc[index, 'top_pro_counts'] = frame_counts_pro[-1]
        df.loc[index, 'top_pro_percent'] = frame_counts_pro[-1] / float(np.sum(frame_counts_pro))
        if frame_counts_pro[-1] - frame_counts_pro[-2] > threshold:
            df.loc[index, 'top_pro'] = order[-1]
        else:
            df.loc[index, 'top_pro'] = -1

        frame_counts_anti = list((np.array([row[f + '_anti'] for f in FRAMES_COMBO])).tolist())        
        order = np.argsort(frame_counts_anti)

        frame_counts_anti.sort()
        df.loc[index, 'd_anti'] = frame_counts_anti[-1] - frame_counts_anti[-2]
        df.loc[index, 'd_anti_percent'] = (frame_counts_anti[-1] - frame_counts_anti[-2]) / float(np.sum(frame_counts))
        df.loc[index, 'top_anti_counts'] = frame_counts_anti[-1]
        df.loc[index, 'top_anti_percent'] = frame_counts_anti[-1] / float(np.sum(frame_counts_anti))
        if frame_counts_anti[-1] - frame_counts_anti[-2] > threshold:
            df.loc[index, 'top_anti'] = order[-1]
        else:
            df.loc[index, 'top_anti'] = -1

    return df


def compute_js_divergence_over_time(df):
    df['jsd_temporal'] = 0
    prev_dist = None
    for i, index in enumerate(df.index):
        row = df.loc[index]
        dist_i = np.array([row[f] for f in FRAMES_COMBO])
        dist_i = dist_i / np.sum(dist_i)
        if i > 0:
            M = (dist_i + prev_dist)/2.0
            KLD_current = np.sum(dist_i * np.log(dist_i / M))
            KLD_prev = np.sum(prev_dist * np.log(prev_dist / M))
            df.loc[index, 'jsd_temporal'] = (KLD_current + KLD_prev)/2.0
        prev_dist = dist_i
    return df


def load_polls(filename, first_year, last_date=None, subcode=None, n_folds=5, last_year=None):
    """
    Load the polling data from a .csv file
    :param filename (str): The file containing the polling data
    :param first_year (int): Exclude polls before this year
    :param last_date (date): Exclude polls after this date
    :param subcode (int): If not None, only include polls with this subcode
    :return A DataFrame of polling data
    """

    df = pd.read_csv(filename)
    nRows, nCols = df.shape

    df['date'] = [pd.Timestamp(dt.datetime.strptime(str(d), '%m/%d/%Y')) for d in df['Date']]
    #df['date'] = [pd.Timestamp(d) for d in df['Date']]

    df = convert_dates(df, first_year)
    
    df['value'] = df['Index'].as_matrix() / 100.0

    # transform poll values in range (0-1) to R
    df['transformed'] = np.log(df.value / (1 - df.value))

    # only include polls with N > 0
    df = df[df['N'] > 1]

    # filter by date
    df = df[df['date'] >= pd.datetime(first_year, 1, 1)]
    if last_date is not None:
        df = df[df['date'] <= last_date]  
    if last_year is not None:
        df = df[df['date'] <= pd.datetime(last_year, 12, 31)]  

    # sort the polls by date
    df = df.sort_values(by='date')
    df = convert_dates(df, first_year)
    
    nRows, nCols = df.shape
    folds = np.tile(np.arange(n_folds), nRows // n_folds + 1)[:nRows]
    df['fold'] = folds

    return df


def combine_polls_with_preceeding_articles(polls, data, n_days=30, include_tone=True, include_frames=True):
    # summarize the tone and framing from the articles preceding each poll, and add it to the poll data
    df = polls.copy()

    df['pStories'] = 0
    if include_tone:
        df['pTone'] = 0
    if include_frames:
        for f in FRAMES:
            df['p' + f] = 0
    for i, index in enumerate(polls.index):
        date_i = polls.loc[index, 'date']
        articles = data[(data['date'] <= date_i) & (data['date'] > date_i - dt.timedelta(n_days))]
        n_articles, _ = articles.shape
        article_mean = articles.mean(axis=0)

        df.loc[index, 'pStories'] = n_articles
        if include_tone:
            df.loc[index, 'pTone'] = article_mean.tone

        if include_frames:
            df.loc[index, 'pEntropy'] = entropy([article_mean[f] for f in FRAMES])
            for f in FRAMES:
                df.loc[index, 'p' + f] = article_mean[f]

    df['pToneXpStories'] = df['pTone'] * df['pStories']
    df['pToneXpEntropy'] = df['pTone'] * df['pEntropy']    
    df['pLogStories'] = np.log(df['pStories'].values) - np.mean(np.log(df['pStories'].values))
    df['pToneXpLogStories'] = df['pTone'] * df['pLogStories']
    return df


def get_top_poll_questions(polls, n=10):
    varname_counts = Counter()
    varname_counts.update(polls['Varname'].ravel())
    top_varnames = [k for k, c in varname_counts.most_common(n=n)]
    return top_varnames

