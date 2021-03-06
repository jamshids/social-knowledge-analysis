import os
import sys
import copy
import json
import logging
import numpy as np


def set_up_logger(log_name, logfile_path, logger_disable, file_mode='w'):
    """Setting up handler of the "root" logger as the single main logger
    """
    
    logger = logging.getLogger(log_name)
    if logger_disable:
        handler = logging.NullHandler()
    elif logfile_path is None:
        handler = logging.StreamHandler()
    else:
        logger.setLevel(logging.INFO)
        handler = logging.FileHandler(filename=logfile_path,
                                      encoding='utf-8',
                                      mode=file_mode)
    handler.setFormatter(logging.Formatter("%(asctime)s : %(levelname)s : %(message)s"))
    logger.handlers = []
    logger.addHandler(handler)

    return logger

def locate_array_in_array(moving_arr, fixed_arr):
    """For each overlapping element in moving_arr, find its location 
    index in fixed_arr

    The assumption is that moving the array is a subset of the fixed array
    """

    assert np.sum(np.isin(moving_arr, fixed_arr))==len(moving_arr), \
        'Moving array should be a subset of fixed array.'
    
    sinds = np.argsort(fixed_arr)
    locs_in_sorted = np.searchsorted(fixed_arr[sinds], moving_arr)

    return sinds[locs_in_sorted]


def find_studied_ents_VW(ents,VW,row_yrs,yr):
    """Generating entities that have been studied prior to the input 
    year based on a given vertex-weight matrix 

    Here, it is assumed that VW (vertex weight matrix) contains only
    the entity+property columns (i.e., author columns are excluded).
    """

    assert len(ents)==(VW.shape[1]-1), 'Number of columns in the vertex weight ' +\
        'matrix should equal the number of given entities.'

    assert len(row_yrs)==VW.shape[0], 'Number of rows in the vertex weight ' +\
        'matrix should equal the number of given years.'

    sub_VW = VW[row_yrs<yr,:]
    studied_bin = np.asarray(np.sum(sub_VW[:,:-1].multiply(sub_VW[:,-1]), axis=0)>0)[0,:]
    return ents[studied_bin]
    

def find_studied_ents_linksdict(file_or_dict,yr):
    """Generating entities that have been studied prior to the input 
    year (excluding that year) based on a dictionary of the form:
    {E1:Y1, E2:Y2, ...}
    where Ei's are the entities and Yi's are the corresponding years that the 
    relationship between Ei's and the property are obtained (curated).
    """

    if isinstance(file_or_dict,str):
        link_dict = json.load(open(file_or_dict,'r'))
    elif isinstance(file_or_dict, dict):
        link_dict = file_or_dict
    else:
        raise ValueError('The first input should be either a string (path ' +\
                         'to file) or a dictionary.')

    return np.array([x for x,y in link_dict.items() if y<yr])


def gt_discoveries(ents,VW,row_yrs,constraint_func=None):
    """Generating ground truth discoveries in a given year
    """

    assert len(ents)==(VW.shape[1]-1), 'Number of columns in the vertex weight ' +\
                'matrix should equal the number of given entities.'

    assert len(row_yrs)==VW.shape[0], 'Number of rows in the vertex weight ' +\
        'matrix should equal the number of given years.'

    def gt_disc_func(year_of_gt):

        sub_VW = VW[row_yrs==year_of_gt,:]
        studied_bin = np.asarray(np.sum(sub_VW[:,:-1].multiply(sub_VW[:,-1]), axis=0)>0)[0,:]
        all_studied_ents = ents[studied_bin]
        # remove already studied ones
        prev_studied_ents = find_studied_ents_VW(ents,VW,row_yrs,year_of_gt)

        disc_ents = all_studied_ents[~np.isin(all_studied_ents,prev_studied_ents)]

        if constraint_func is not None:
            disc_ents = constraint_func(disc_ents)
        
        return disc_ents

    return gt_disc_func


def gt_discoveries_4CTD(disease):

    ds_dr_path = '/home/jamshid/codes/data/CTD/diseases_drugs.json'
    target_ds_dr = json.load(open(ds_dr_path, 'r'))
    rel_drugs = target_ds_dr[disease]

    def gt_disc_func(yr):
        gt = np.array([x.lower() for x,y in rel_drugs.items() if int(y)==yr])
        gt = np.array([x.replace(' ','_') for x in gt])
        return gt

    return gt_disc_func


def prune_deepwalk_sentences(sents, remove='author'):

    # removing authors or chemicals
    if remove=='author':
        hl = [[s for s in h.split(' ') if 'a_' not in s] for h in sents]
    elif remove=='chemical':
        hl = [[s for s in h.split(' ') if ('a_' in s) or ('thermoelectric' in s)]
              for h in sents]
    elif remove=='author_affiliation':
        hl = [[s for s in h.split(' ') if '_' not in s] for h in sents]

    # rejoining the split terms and ignoring those with singular terms
    hl = [' '.join(h) for h in hl if len(h)>1]

    # removing dots
    hl = [h.split('.')[0] for h in hl]

    # removing those sentences only containing the keyword
    hl = [h for h in hl if len(np.unique(h.split(' ')))>1]

    return hl


def lighten_color(color, amount=0.5):
    """
    Downloaded
    -----------
    This piece of code is downloaded from
    https://stackoverflow.com/a/49601444/8802212

    Lightens the given color by multiplying (1-luminosity) by the given amount.
    Input can be matplotlib color string, hex string, or RGB tuple.

    Examples:
    >> lighten_color('g', 0.3)
    >> lighten_color('#F034A3', 0.6)
    >> lighten_color((.3,.55,.1), 0.5)
    """
    import matplotlib.colors as mc
    import colorsys
    try:
        c = mc.cnames[color]
    except:
        c = color
    c = colorsys.rgb_to_hls(*mc.to_rgb(c))
    return colorsys.hls_to_rgb(c[0], 1 - amount * (1 - c[1]), c[2])
