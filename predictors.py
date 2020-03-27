import os
import sys
import pdb
import logging
import numpy as np
from scipy import sparse

from gensim.models import Word2Vec

path = '/home/jamshid/codes/social-knowledge-analysis'
sys.path.insert(0, path)

import measures
import hypergraphs
from misc import helpers
from data import utils, readers

config_path = '/home/jamshid/codes/data/sql_config_0.json'
msdb = readers.MatScienceDB(config_path, 'msdb')


def ySD(cocrs, ySD, years_of_cocrs_columns, **kwargs):
    """Returning a discovery predictor based on yearwise SD metric
    """

    memory = kwargs.get('memory', 5)
    scalarization = kwargs.get('scalarization', 'SUM')
    pred_size = kwargs.get('pred_size', 50)

    # get all chemicals
    msdb.crsr.execute('SELECT formula FROM chemical;')
    chems = np.array([x[0] for x in msdb.crsr.fetchall()])

    def ySD_predictor(year_of_pred, sub_chems):

        if sub_chems is not None:
            overlap_indic = np.in1d(chems, sub_chems)
            sub_cocrs = cocrs[overlap_indic, :]
            sub_ySD  = ySD[overlap_indic, :]
        else:
            sub_chems = chems
            sub_cocrs = cocrs
            sub_ySD = ySD

        """ Restricting Attention to Unstudied Materials """
        yr_loc = np.where(years_of_cocrs_columns==year_of_pred)[0][0]
        unstudied_indic = np.sum(sub_cocrs[:,:yr_loc], axis=1)==0
        sub_chems = sub_chems[unstudied_indic]
        sub_ySD = sub_ySD[unstudied_indic,:yr_loc]

        """ Computing and Sorting Scores """ 
        scores = measures.ySD_scalar_metric(sub_ySD,
                                            mtype=scalarization,
                                            memory=memory)

        sorted_inds = np.argsort(-scores)[:pred_size]

        return sub_chems[sorted_inds]

    return ySD_predictor


def embedding(cocrs, years_of_cocrs_columns, model_or_path, y_term, **kwargs):

    pred_size = kwargs.get('pred_size', 50)
    
    # get all chemicals
    msdb.crsr.execute('SELECT formula FROM chemical;')
    chems = np.array([x[0] for x in msdb.crsr.fetchall()])

    if isinstance(model_or_path, str):
        model = Word2Vec.load(model_or_path)
    else:
        model = model_or_path

    
    def embedding_predictor(year_of_pred, sub_chems):

        # embedding-based predictions can only work with subset of chemicals
        # that exist in the vocabulary of their pre-trained model
        overlap_indic = np.in1d(chems, sub_chems)
        sub_cocrs = cocrs[overlap_indic, :]
        
        """ Restricting Attention to Unstudied Materials """
        yr_loc = np.where(years_of_cocrs_columns==year_of_pred)[0][0]
        unstudied_indic = np.sum(sub_cocrs[:,:yr_loc], axis=1)==0
        sub_chems = sub_chems[unstudied_indic]

        """ Computing and Sorting Scores """
        scores = measures.cosine_sims(model, sub_chems, y_term)

        sorted_inds = np.argsort(-scores)[:pred_size]

        return sub_chems[sorted_inds]

    return embedding_predictor

def embedding_SD_lincomb(cocrs,
                         ySD,
                         years_of_cocrs_columns,
                         path_to_wvmodel,
                         y_term,
                         **kwargs):
    """Linear combination of embedding- and SD-based predictions
    """

    pred_size = kwargs.get('pred_size', 50)
    beta = kwargs.get('beta', 0.5)
    memory = kwargs.get('memory', 5)
    scalarization = kwargs.get('scalarization', 'SUM')


    assert 0<beta<1, 'beta should be between zero and one.'

    # get all chemicals
    msdb.crsr.execute('SELECT formula FROM chemical;')
    chems = np.array([x[0] for x in msdb.crsr.fetchall()])

    model = Word2Vec.load(path_to_wvmodel)

    def embedding_SD_predictor(year_of_pred, sub_chems):
        
        # Similar to embedding-based predictions, this predictor 
        # also can only work with subset of chemicals 
        # that exist in the vocabulary of their pre-trained model
        overlap_indic = np.in1d(chems, sub_chems)
        sub_cocrs = cocrs[overlap_indic, :]
        sub_ySD = ySD[overlap_indic, :]
        
        """ Restricting Attention to Unstudied Materials """
        yr_loc = np.where(years_of_cocrs_columns==year_of_pred)[0][0]
        unstudied_indic = np.sum(sub_cocrs[:,:yr_loc], axis=1)==0
        sub_chems = sub_chems[unstudied_indic]
        sub_ySD = sub_ySD[unstudied_indic,:yr_loc]

        """ Two Types of Scores """
        scores_0 = measures.ySD_scalar_metric(sub_ySD,
                                              mtype=scalarization,
                                              memory=memory)
        scores_1 = measures.cosine_sims(model, sub_chems, y_term)

        """ Normalizing Scores' Scales """
        scores_0 = (scores_0 - scores_0.min()) / (scores_0.max() - scores_0.min())
        scores_1 = (scores_1 - scores_1.min()) / (scores_1.max() - scores_1.min())

        """ Combining and Sorting Scores """
        scores = beta*scores_1 + (1-beta)*scores_0
        sorted_inds = np.argsort(-scores)[:pred_size]

        return sub_chems[sorted_inds]

    return embedding_SD_predictor

def hypergraph_access(cocrs,
                      years_of_cocrs_columns,
                      path_to_VM_core,
                      path_to_VM_kw,
                      **kwargs):
    
    VM = sparse.load_npz(path_to_VM_core)
    kwVM = sparse.load_npz(path_to_VM_kw)
    R = sparse.hstack((VM, kwVM), 'csc')

    pred_size = kwargs.get('pred_size', 50)
    nstep = kwargs.get('nstep', 1)
    memory = kwargs.get('memory', 5)
    scalarization = kwargs.get('scalarization', 'SUM')

    # get all chemicals
    msdb.crsr.execute('SELECT formula FROM chemical;')
    chems = np.array([x[0] for x in msdb.crsr.fetchall()])

    def access_score(year_of_pred, sub_chems):
        
        if sub_chems is not None:
            overlap_indic = np.in1d(chems, sub_chems)
            sub_cocrs = cocrs[overlap_indic, :]
        else:
            sub_chems = chems
            sub_cocrs = cocrs

        """ Restricting Attention to Unstudied Materials """
        yr_loc = np.where(years_of_cocrs_columns==year_of_pred)[0][0]
        unstudied_indic = np.sum(sub_cocrs[:,:yr_loc], axis=1)==0
        sub_chems = sub_chems[unstudied_indic]

        scores = measures.accessibility_scalar_metric(R,
                                                      year_of_pred,
                                                      memory,
                                                      sub_chems=sub_chems,
                                                      nstep=nstep,
                                                      mtype=scalarization)

        sorted_inds = np.argsort(-scores)[:pred_size]

        return sub_chems[sorted_inds]

    return access_score


def random_deepwalk(cocrs,
                    years_of_cocrs_columns,
                    path_to_deepwalk,
                    **kwargs):

    pred_size = kwargs.get('pred_size', 50)

    # get all chemicals
    msdb.crsr.execute('SELECT formula FROM chemical;')
    chems = np.array([x[0] for x in msdb.crsr.fetchall()])

    # chemicals in the deepwalk
    deepwalk_chems = hypergraphs.extract_chems_from_deepwalks(path_to_deepwalk)
    
    def random_deepwalk_predictor(year_of_pred, sub_chems):
        
        if sub_chems is not None:
            overlap_indic = np.in1d(chems, sub_chems)
            sub_cocrs = cocrs[overlap_indic, :]
        else:
            sub_chems = chems
            sub_cocrs = cocrs

        """ Restricting Attention to Unstudied Materials """
        yr_loc = np.where(years_of_cocrs_columns==year_of_pred)[0][0]
        unstudied_indic = np.sum(sub_cocrs[:,:yr_loc], axis=1)==0
        sub_chems = sub_chems[unstudied_indic]

        # randomly choosing chemicals from those that exist in the deepwalks
        deepwalk_sub_chems = deepwalk_chems[np.isin(deepwalk_chems, sub_chems)]
        
        np.random.shuffle(deepwalk_sub_chems)
        return deepwalk_sub_chems[:pred_size]

    return random_deepwalk_predictor
    

def hypergraph_author_accesss(path_to_VM_core,
                              path_to_VM_kw,
                              **kwargs):

    VM = sparse.load_npz(path_to_VM_core)
    kwVM = sparse.load_npz(path_to_VM_kw)
    R = sparse.hstack((VM, kwVM), 'csc')

    pred_size = kwargs.get('pred_size', 50)
    nstep = kwargs.get('nstep', 1)
    memory = kwargs.get('memory', 5)

    # get all chemicals
    msdb.crsr.execute('SELECT formula FROM chemical;')
    chems = np.array([x[0] for x in msdb.crsr.fetchall()])

    def author_access_scores(year_of_pred, size=0):

        if size==0:
            size=pred_size
        
        scores = measures.author_accessibility_scalar_score(R,
                                                            year_of_pred,
                                                            memory)

        sorted_inds = np.argsort(-scores)[:size]

        return sorted_inds

    return author_access_scores


