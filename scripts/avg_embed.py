"""This script averages all embeddings for each Pfam family and saves the average embedding as
a numpy array in a new directory.

__author__= "Ben Iovino"
__date__ = "05/12/23"
"""

import argparse
import os
import logging
import numpy as np
from Bio import SeqIO


def get_seqs(family: str) -> dict:
    """Returns a dictionary of sequences for a given Pfam family.

    :param family: name of Pfam family
    :return: seq id is key with sequence as value
    """

    sequences = {}
    with open(f'data/families_gaps/{family}/seqs.fa', 'r', encoding='utf8') as file:
        for record in SeqIO.parse(file, 'fasta'):
            sequences[record.id] = record.seq  # Add sequence to dictionary

    return sequences


def cons_pos(sequences: dict) -> dict:
    """It returns a dict with the positions that are included in the consensus for each sequence
    in a dictionary.

    :param sequences: dictionary of sequences
    :return: seq id is key with list of positions as value
    """

    # Get consensus sequence and remove it so it is not compared to itself
    cons_seq = sequences['consensus']
    del sequences['consensus']

    # For each sequence, compare to consensus to get positions of non-gap characters
    positions = {}
    for seqid, seq in sequences.items():  # pylint: disable=W0612
        pos_list = []
        for i, pos in enumerate(cons_seq):
            if pos != '.' and seq[i] != '.':  # If both are not gaps
                pos_list.append(i)
        positions[seqid] = pos_list

    return positions


def get_embed(direc: str, sequences: dict) -> dict:
    """Returns a dictionary of embeddings corresponding to the consensus positions for
    each sequence.

    :param family: name of Pfam family
    :param sequences: dict where seq id is key with sequence as value
    :return: dict where seq id is key with list of embeddings as value
    """

    # Load embeddings from file
    embeddings = {}
    embed = np.load(f'{direc}/embed.npy', allow_pickle=True)
    for sid, emb in embed:
        embeddings[sid] = emb

    # Pad embeddings to match length of consensus sequence
    for seqid, embed in embeddings.items():
        sequence = sequences[seqid]

        # Pad embeddings with 0s where there are gaps in the aligned sequences
        count, pad_emb = 0, []
        for pos in sequence:
            if pos == '.':
                pad_emb.append(0)
            elif pos != '.':
                pad_emb.append(embed[count])
                count += 1
        embeddings[seqid] = pad_emb

    return embeddings


def average_embed(family: str, positions: dict, embeddings: dict):
    """Saves a list of vectors that represents the average embedding for each
    position in the consensus sequence for each Pfam family.

    :param family: name of Pfam family
    :param sequences: dict where seq id is key with sequence as value
    :param positions: dict where seq id is key with list of positions as value
    """

    # Create a dict of lists where each list contains the embeddings for a position in the consensus
    seq_embed = {}
    for seqid, position in positions.items():  # Go through positions for each sequence
        for pos in position:
            if pos not in seq_embed:  # Initialize key and value
                seq_embed[pos] = []
            seq_embed[pos].append(embeddings[seqid][pos])  # Add embedding to list for that pos

    # Sort dictionary by key (out of order for some reason)
    seq_embed = dict(sorted(seq_embed.items()))

    # Move through each position (list of embeddings) and average them
    avg_embed = []
    for pos, embed in seq_embed.items():
        avg_embed.append(np.mean(embed, axis=0))  # Find mean for each position (float)

    # Save to file
    if not os.path.exists(f'data/avg_embed/{family}'):
        os.makedirs(f'data/avg_embed/{family}')
    with open(f'data/avg_embed/{family}/avg_embed.npy', 'wb') as emb_f:
        np.save(emb_f, avg_embed, allow_pickle=True)


def main():
    """Main goes through each Pfam family and calls get_seqs() to get protein sequences, cons_pos()
    to get the consensus sequence positions, get_embed() to get the embeddings for each sequence,
    and average_embed() to average the embeddings and save them to file.
    """

    # Put log in main because other scripts call functions from this script and will log incorrectly
    log_filename = 'data/logs/avg_embed.log'  #pylint: disable=C0103
    os.makedirs(os.path.dirname(log_filename), exist_ok=True)
    logging.basicConfig(filename=log_filename, filemode='w',
                     level=logging.INFO, format='%(message)s')

    parser = argparse.ArgumentParser()
    parser.add_argument('-d', type=str, default='data/esm2_17_embed', help='direc of embeds to avg')
    args = parser.parse_args()

    for i, family in enumerate(os.listdir(args.d)):
        logging.info('Averaging embeddings for %s, %s', family, i)

        # Check if average embedding already exists
        if os.path.exists(f'data/avg_embed/{family}/avg_embed.npy'):
            continue

        # Get sequences and their consensus positions
        sequences = get_seqs(family)
        positions = cons_pos(sequences)

        # Get embeddings for each sequence in family and average them
        embed_direc = f'{args.d}/{family}'
        embeddings = get_embed(embed_direc, sequences)
        average_embed(family, positions, embeddings)


if __name__ == '__main__':
    main()
