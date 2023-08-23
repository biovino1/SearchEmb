"""This script searches two different databases, first using dct vectors to filter out
dissimilar sequences, then using embeddings to find the most similar sequences.

__author__ = "Ben Iovino"
__date__ = "08/18/23"
"""


import argparse
import datetime
import logging
import os
import pickle
from random import sample
import numpy as np
from Bio import SeqIO
import torch
from util import load_model, Embedding, Transform

log_filename = 'data/logs/search.log'  #pylint: disable=C0103
os.makedirs(os.path.dirname(log_filename), exist_ok=True)
logging.basicConfig(filename=log_filename, filemode='w',
                     level=logging.INFO, format='%(message)s')


def embed_query(
    sequence: str, tokenizer, model, device: str, encoder: str, layer: int) -> Embedding:
    """Returns the embedding of a fasta sequence.

    :param sequence: path to fasta file containing query sequence
    :param tokenizer: tokenizer
    :param model: encoder model
    :param device: cpu or gpu
    :param encoder: prott5 or esm2
    :param layer: layer to extract features from (if using esm2)
    :return: Embedding object containing embedding of query sequence
    """

    # Get seqs from file and randomly sample one
    seqs = {}
    with open(sequence, 'r', encoding='utf8') as f:
        for i, seq in enumerate(SeqIO.parse(f, 'fasta')):
            seqs[i] = (seq.id, str(seq.seq))
    seq = sample(list(seqs.values()), 1)[0]

    # Initialize Embedding object and embed sequence
    embed = Embedding(seq[0], seq[1], None)
    embed.embed_seq(tokenizer, model, device, encoder, layer)

    return embed


def transform_embed(embed: Embedding, args: argparse.Namespace) -> Transform:
    """Returns the DCT of an embedded fasta sequence.

    :param embed: Embedding object
    :param args: argparse.Namespace object containing arguments
    :return: Transform object containing dct representation of query sequence
    """

    transform = Transform(embed.embed[0], embed.embed[1], None)
    transform.quant_2D(args.s1, args.s2)
    if transform.trans[1] is None:  # Skip if DCT is None
        return None  #\\NOSONAR

    return transform


def clan_results(query_fam: str, results_fams: list) -> int:
    """Returns 1 if query and top result are in the same clan, 0 otherwise.

    :param query_fam: family of query sequence
    :param results_fams: list of families of top N results
    :return: 1 if query and top result are in the same clan, 0 otherwise
    """

    with open('data/clans.pkl', 'rb') as file:
        clans = pickle.load(file)
    for fams in clans.values():
        if query_fam in fams and results_fams[0] in fams:
            return 1
    return 0


def search_results(query: str, results: dict, counts: dict) -> dict:
    """Returns a dict of counts for matches, top n results, and same clan for all queries in a
    search.

    :param query: query sequence
    :param results: dictionary of results from searching query against dcts
    :param counts: dictionary of counts for matches, top n results, and same clan
    :param top: number of results to return
    :return: dict of counts for matches, top n results, and same clan
    """

    # Log time and similarity for top 5 results
    logging.info('%s\n%s', datetime.datetime.now(), query)
    for fam, sim in list(results.items())[:5]:
        logging.info('%s,%s', fam, sim)

    # See if query is in top results
    results_fams = [fam.split('/')[0] for fam in results.keys()]
    query_fam = query.split('/')[0]
    counts['total'] += 1
    if query_fam == results_fams[0]:  # Top result
        counts['match'] += 1
        return counts
    if query_fam in results_fams:  # Top n results
        counts['top'] += 1
        return counts
    counts['clan'] += clan_results(query_fam, results_fams)  # Same clan

    return counts


def main():
    """Searches two different databases, first using dct vectors to filter out dissimilar sequences.
    If top result is not same as query family, then searches embeddings database.
    """

    parser = argparse.ArgumentParser()
    parser.add_argument('-dct', type=str, default='data/esm2_17_875_avg.npy')
    parser.add_argument('-emb', type=str, default='data/anchors.npy')
    parser.add_argument('-e', type=str, default='esm2')
    parser.add_argument('-l', type=int, default=17)
    parser.add_argument('-t', type=int, default=100)
    parser.add_argument('-s1', type=int, default=8)
    parser.add_argument('-s2', type=int, default=75)
    args = parser.parse_args()

    # Load tokenizer and encoder
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')  # pylint: disable=E1101
    tokenizer, model = load_model(args.e, device)

    # Load embed/dct database
    dct_db = np.load(args.dct, allow_pickle=True)
    dct_fams = [transform[0] for transform in dct_db]
    emb_db = np.load(args.emb, allow_pickle=True)

    # Call query_search for every query sequence in a folder
    counts = {'match': 0, 'top': 0, 'clan': 0, 'total': 0}
    direc = 'data/full_seqs'
    for fam in os.listdir(direc):
        if fam not in dct_fams:  # Skip if family not in database
            continue

        # Randomly sample one query from family and get embedding and dct
        seq_file = f'{direc}/{fam}/seqs.fa'
        embed = embed_query(seq_file, tokenizer, model, device, args.e, args.l)
        dct = transform_embed(embed, args)
        if dct is None:
            logging.info('%s\n%s\nQuery was too small for transformation dimensions',
                          datetime.datetime.now(), embed.embed[0])
            continue

        # Search dct db - check if top family is same as query family
        results = dct.search(dct_db, args.t)
        results_fams = [fam.split('/')[0] for fam in results.keys()]
        if fam == results_fams[0]:
            counts = search_results(f'{fam}/{dct.trans[0]}', results, counts)
            logging.info('DCT: Queries: %s, Matches: %s, Top%s: %s, Clan: %s\n',
                      counts['total'], counts['match'], args.t, counts['top'], counts['clan'])
            continue

        # If top family is not same as query family, search anchors on top results from DCTs
        results = embed.search(emb_db, args.t, results_fams)
        counts = search_results(f'{fam}/{embed.embed[0]}', results, counts)
        logging.info('ANCHORS: Queries: %s, Matches: %s, Top%s: %s, Clan: %s\n',
                      counts['total'], counts['match'], args.t, counts['top'], counts['clan'])


if __name__ == '__main__':
    main()
