import os
import sys
import pdb
import json
import logging
import pymysql
import pdb
import numpy as np

from gensim.models import Word2Vec


path = '/home/jamshid/codes/social-knowledge-analysis'
sys.path.insert(0, path)

from data import readers
from misc import helpers
config_path = '/home/jamshid/codes/data/sql_config_0.json'
msdb = readers.MatScienceDB(config_path, 'msdb')

def hypergraph_trans_prob_length2(kws_set, chms_set, **kwargs):
    """Computing the transition probability of length-2 paths from w1 to w2
    through author an node
    """
    
    # setting up the logger
    logger_disable = kwargs.get('logger_disable', False)
    logfile_path =   kwargs.get('logfile_path', None)
    logger = helpers.set_up_logger(__name__, logfile_path, logger_disable)

    msdb.crsr.execute('SELECT COUNT(*) FROM paper;')
    logger.info('Total number of documents in the DB: {}'.format(
        msdb.crsr.fetchall()[0][0]))

    years = kwargs.get('years', [])
    
    # getting author neighbors of w1 (possibly have repetitive entries)
    case_sensitives = kwargs.get('case_sensitives',[])
    R = msdb.get_authors_by_keywords(kws_set,
                                     case_sensitives=case_sensitives,
                                     years=years,
                                     logical_comb='OR',
                                     return_papers=True)
    Gamma_A_w1 = np.array(R['author_id'])
    ew1 = np.array(R['paper_id'])
    uGamma_A_w1 = np.unique(Gamma_A_w1)
    
    # degree of w1 (# papers that includes w1)
    u_ew1 = np.unique(ew1)
    dw1 = len(u_ew1)

    logger.info('Number of author nodes neighbor to the first set of words: {}'.format(
        len(Gamma_A_w1)))
    logger.info('Number of distinct neighboring authors nodes: {}'.format(
        len(uGamma_A_w1)))
    logger.info('Number of hyperedges (papers) that contain the first set of words: {}'.format(
        dw1))

    # in each part of the following loop, we will need degree of the "common"
    # author nodes. Hence, we can compute all these degrees once for all before the
    # loop:
    da_vec = msdb.get_NoP_by_author_ids(uGamma_A_w1, years=years)
    da_vec = np.array([da_vec[x] for x in uGamma_A_w1])

    # another thing that we can compute before the loop, is the size of papers
    # that contain {a,w1}, because we do have access to all such papers in ew1
    # (or equivalently, its distinct values in u_ew1)
    # VERIFIED: .values method of a dictionary does not change order of the keys
    d_ew1 = np.array(list(get_size_of_papers(list(u_ew1)).values())) + 1
    # +1 is to take into account the property-keyword itself
    

    # Now go through all the second set of words
    save_dirname = kwargs.get('save_dirname', None)
    trans_probs = np.zeros(len(chms_set))
    for i, w2 in enumerate(chms_set):

        if not((i-1)%500) and i>0:
            logger.info('{} materials processed. \n\tMin. of trans. probs.: {} \
                         \n\t Max. of trans. probs.: {} \
                         \n\t Av. of trans. probs.: {}'.format(i-1,
                                                               np.min(trans_probs[:i]),
                                                               np.max(trans_probs[:i]),
                                                               np.mean(trans_probs[:i])))
            if save_dirname is not None:
                np.savetxt(os.path.join(save_dirname, 'hyper_transprob_len1.txt'), trans_probs)

        
        R = msdb.get_authors_by_chemicals([w2], 
                                          years=years,
                                          return_papers=True)
        if len(R)==0:
            continue
        else:
            R = R[w2]
            
        Gamma_A_w2 = R['author_id']
        uGamma_A_w2 = np.unique(Gamma_A_w2)
        ew2 = R['paper_id']
        dw2 = len(np.unique(ew2))
        
        # get intersection of Gamma_A_w1 and Gamma_A_w2
        overlap_idx = np.in1d(uGamma_A_w1, uGamma_A_w2)
        CAs = uGamma_A_w1[overlap_idx]
        CAs_da = da_vec[overlap_idx]

        trans_prob = 0
        for ii, a in enumerate(CAs):
            da = CAs_da[ii]

            # e: {w1,a} in e
            e_w1a = ew1[Gamma_A_w1==a]
            e_w1a_sizes = d_ew1[np.in1d(u_ew1, e_w1a)]

            # e: {w2,a} in e
            e_w2a = ew2[Gamma_A_w2==a]
            e_w2a_sizes = np.array(list(get_size_of_papers(list(e_w2a)).values()))

            trans_prob += (1/da)*np.sum(1/e_w1a_sizes)*np.sum(1/e_w2a_sizes)

        trans_probs[i] = 0.5*(1/dw1 + 1/dw2)*trans_prob
        
    return trans_probs


def get_size_of_papers(paper_ids):
    """Computing size of a hyperedge associated with the given paper ID

    Each paper hyperedge consists of certain number of author nodes and
    possibly some conceptual nodes (chemicals in case of materials papers).
    Size of a hyperedge is equal to the number of nodes (of all types) that
    it contains
    """
    
    # number of authors
    NoA = msdb.get_NoA_by_paper_ids(paper_ids)
    for i in set(paper_ids)-set(NoA):
        NoA[i] = 0
    
    # number of concepts (chemical nodes)
    NoC = msdb.get_NoC_by_paper_ids(paper_ids)
    for i in set(paper_ids)-set(NoC):
        NoC[i] = 0

    sizes = {i: NoA[i]+NoC[i] for i in paper_ids}
    

    return sizes
        