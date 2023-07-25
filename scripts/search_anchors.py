"""================================================================================================
This script takes a query sequence and a list of anchor sequences and searches for the most
similar anchor sequence.

Ben Iovino  05/24/23   SearchEmb
================================================================================================"""

import argparse
import datetime
import logging
import os
import pickle
from random import sample
from Bio import SeqIO
import numpy as np
import torch
from util import load_model, Embedding
from scipy.spatial.distance import cityblock

log_filename = 'data/logs/search_anchors.log'  #pylint: disable=C0103
os.makedirs(os.path.dirname(log_filename), exist_ok=True)
logging.basicConfig(filename=log_filename, filemode='w',
                     level=logging.INFO, format='%(message)s')


def embed_query(sequence: str, tokenizer, model, device, args: argparse.Namespace) -> np.ndarray:
    """=============================================================================================
    This function loads a query sequence from file and embeds it using the provided tokenizer and
    encoder.

    :param sequence: path to fasta file containing query sequence
    :param tokenizer: tokenizer
    :param model: encoder model
    :param device: cpu or gpu
    :return np.ndarray: embedding of query sequence
    ============================================================================================="""

    seq = ()
    with open(sequence, 'r', encoding='utf8') as f:
        for seq in SeqIO.parse(f, 'fasta'):
            seq = (seq.id, str(seq.seq))

    # Initialize Embedding object and embed sequence
    embed = Embedding(seq[0], seq[1], None)
    embed.embed_seq(tokenizer, model, device, args.e, args.l)

    return embed.embed[1]


def query_sim(anchor: np.ndarray, query: np.ndarray, sims: dict, family: str, metric: str) -> dict:
    """=============================================================================================
    This function takes an anchor embedding (1D array) and a query embedding (2D array) and finds
    the similarity between the anchor and each embedding in the query.

    :param anchor: embedding of anchor sequence
    :param query: embedding of query sequence
    :param sims: dictionary of similarities between anchor and query embeddings
    :param family: name of anchor family
    :param metric: similarity metric
    :return sims: updated dictionary
    ============================================================================================="""

    sim_list = []
    for embedding in query:

        # Cosine similarity between anchor and query embedding
        if metric == 'cosine':
            sim = np.dot(anchor, embedding) / \
                (np.linalg.norm(anchor) * np.linalg.norm(embedding))
            sim_list.append(sim)

        # City block distance between anchor and query embedding
        if metric == 'cityblock':
            dist = 1/cityblock(anchor, embedding)
            sim_list.append(dist)

        # Find most similar embedding of query to anchor
        max_sim = max(sim_list)
        sims[family].append(max_sim)

        # Compare similarity to first anchor to average similarities of rest of results
        if len(sims[family]) == 1 and len(sims) > 100:
            if max_sim < np.mean(list(sims.values())[100]):
                break  # If similarity is too low, stop comparing to rest of anchors

    return sims


def query_search(query: np.ndarray, anchors: str, results: int, metric: str) -> dict:
    """=============================================================================================
    This function takes a query embedding, a directory of anchor embeddings, and returns a dict
    of the top n most similar anchor families.

    :param query: embedding of query sequence
    :param anchors: directory of anchor embeddings
    :param results: number of results to return
    :param metric: similarity metric
    :return top_sims: dict where keys are anchor families and values are similarity scores
    ============================================================================================="""

    # Search query against every set of anchors
    sims = {}
    for family in os.listdir(anchors):
        anchors = f'data/anchors/{family}/anchor_embed.npy'
        ancs_emb = np.load(anchors)

        # I think np.load loads a single line as a 1D array, so convert to 2D or else
        # max_sim = max(cos_sim) will throw an error
        if len(ancs_emb) == 1024:
            ancs_emb = [ancs_emb]

        # Add family to sims dict
        if family not in sims:
            sims[family] = []

        # Compare every anchor embedding to query embedding
        for anchor in ancs_emb:
            sims = query_sim(anchor, query, sims, family, metric)
        sims[family] = np.mean(sims[family])

    # Sort sims dict and return top n results
    top_sims = {}
    for key in sorted(sims, key=sims.get, reverse=True)[:results]:
        top_sims[key] = sims[key]

    return top_sims


def search_results(query: str, results: dict):
    """=============================================================================================
    This function compares a query sequence to a dictionary of results.

    :param query: query sequence
    :param results: dictionary of results from searching query against anchors
    ============================================================================================="""

    # Log time and similarity for top 5 results
    logging.info('%s\n%s', datetime.datetime.now(), query)
    for fam, sim in list(results.items())[:5]:
        logging.info('%s,%s', fam, sim)

    # See if query is in top results
    query_fam = query.split('/')[0]
    match, top, clan = 0, 0, 0
    if query_fam == list(results.keys())[0]:  # Top result
        match += 1
        return match, top, clan
    if query_fam in results:  # Top n results
        top += 1
        return match, top, clan

    # Read clans dict and see if query is in same clan as top result
    with open('data/clans.pkl', 'rb') as file:
        clans = pickle.load(file)
    for fams in clans.values():
        if query_fam in fams and list(results.keys())[0] in fams:
            clan += 1
            return match, top, clan

    return match, top, clan


def main():
    """=============================================================================================
    Main function loads tokenizer and model, randomly samples a query sequence from a family, embeds
    the query, searches the query against anchors, and logs the results
    ============================================================================================="""

    parser = argparse.ArgumentParser()
    parser.add_argument('-d', type=str, default='data/anchors')
    parser.add_argument('-e', type=str, default='prott5')
    args = parser.parse_args()

    # Load tokenizer and encoder
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')  # pylint: disable=E1101
    tokenizer, model = load_model(args.e, device)

    # Call query_search for every query sequence in a folder
    match, top, clan, total = 0, 0, 0, 0
    direc = 'data/full_seqs'
    for fam in os.listdir(direc):

        # Only search families with anchors
        if fam not in os.listdir(args.d):
            continue

        # Randomly sample one query from family
        queries = os.listdir(f'{direc}/{fam}')
        query = sample(queries, 1)[0]
        seq_file = f'{direc}/{fam}/{query}'
        embed = embed_query(seq_file, tokenizer, model, device, args)

        # Search anchors and analyze results
        results = query_search(embed, args.d, 100, 'cosine')
        m, t, c = search_results(f'{fam}/{query}', results)
        (match, top, clan, total) = (match + m, top + t, clan + c, total + 1)
        logging.info('Queries: %s, Matches: %s, Top10: %s, Clan: %s\n', total, match, top, clan)


if __name__ == '__main__':
    main()
