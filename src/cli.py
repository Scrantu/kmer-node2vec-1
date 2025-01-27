# -*- coding: utf-8 -*-
import os
import sys
sys.path.extend(['.', '..'])
import argparse
import gensim
import numpy as np
import networkx as nx
from prettytable import PrettyTable

from src.generators import parse_seq
from src.generators import extract_kmer
from src.generators import save_word2vec_format

from src.kmernode2vec import KMerNode2Vec


class ParameterParser:
    
    def __init__(self, print_params: bool = True):
        self.print_params = print_params
        self.parser = argparse.ArgumentParser(
            description="Run KMer-Node2Vec."
        )
        self.parsed_args = None

    def parameter_parser(self):
        """ A method to parse up command line parameters.

        Note:
            By default it gives an embedding of (...) dataset.
            The default hyperparameters give a good quality representation.
        """

        self.parser.add_argument(
            '--input-seqs-dir',
            nargs='?',
            default='../data_dir/input/',
            help='Sequence files directory.'
        )

        self.parser.add_argument(
            '--edge-list-file',
            nargs='?',
            default='../data_dir/output/edge-list-file.edg',
            help='Edge file path.'
        )

        self.parser.add_argument(
            '--output',
            nargs='?',
            default='../data_dir/output/kmer-embedding.txt',
            help='K-mer embedding path.'
        )

        self.parser.add_argument(
            '--mer',
            nargs='?',
            default=[6, 7, 8],
            help='Length of a sliding window to fragment mer. '
                 'If multiple mers are given, the multi-scale strategy would be employed.'
        )

        self.parser.add_argument(
            '--P',
            type=float,
            default=1.0,
            help='Return hyperparameter. Default is 1.0.'
        )

        self.parser.add_argument(
            '--Q',
            type=float,
            default=0.001,
            help='In-out hyperparameter. Default is 0.001.'
        )

        self.parser.add_argument(
            '--dimensions',
            type=int,
            default=128,
            help='Number of dimensions. Default is 128.'
        )

        self.parser.add_argument(
            '--walk-number',
            type=int,
            default=40,
            help='Number of walks. Default is 40.'
        )

        self.parser.add_argument(
            '--walk-length',
            type=int,
            default=150,
            help='Walk length. Default is 150.'
        )

        self.parser.add_argument(
            '--window-size',
            type=int,
            default=10,
            help='Maximum distance between the current and predicted word within a sentence. Default is 10.'
        )

        self.parser.add_argument(
            '--min-count',
            type=int,
            default=1,
            help='Minimal count. Default is 1.'
        )

        self.parser.add_argument(
            '--workers',
            type=int,
            default=4,
            help='Number of cores. Default is 4.'
        )

        self.parser.add_argument(
            '--epochs',
            type=int,
            default=1,
            help='Number of epochs. Default is 1.'
        )

        if self.print_params is True:
            self._params_printer()

        return self.parser.parse_args()

    def _params_printer(self):
        """ Function to print the logs in a nice table format. """
        parsed_args = vars(self.parser.parse_args())
        table = PrettyTable(["Parameter", "Value"])
        for k, v in parsed_args.items():
            table.add_row([k.replace("_", " ").capitalize(), v])
        print(table)


def main(args):
    pivot_kmers = list()  # store 8-mers
    seqs = parse_seq([args.input_seqs_dir])
    for seq in seqs:
        pivot_kmers.extend(extract_kmer(seq, max(args.mer)))

    kmer2vec_dict = dict()  # save vectors of k-mers in different scales
    for mer in args.mer:
        clf = KMerNode2Vec(
            p=args.P,
            q=args.Q,
            dimensions=args.dimensions,
            num_walks=args.walk_number,
            walks_length=args.walk_length,
            window=args.window_size,
            min_count=args.min_count,
            epochs=args.epochs,
            workers=args.workers,
        )
        clf.fit(
            seqs=seqs,
            mer=mer,
            path_to_edg_list_file=args.edge_list_file,
            # path_to_embeddings_file=args.output,
        )
        kmer2vec_dict.update(clf.get_embedding_dict())

    final_kmer2vec_dict = dict()  # map 8mers to their final multi-scale vectors
    for kmer in pivot_kmers:
        tmp_vecs = list()
        for mer in args.mer:
            vec = 0
            vec_num = len(kmer) - mer + 1
            for i in range(vec_num):
                sub_kmer = kmer[i:i + mer]
                sub_kmer_vec = kmer2vec_dict[sub_kmer]
                vec += sub_kmer_vec
            vec /= vec_num
            tmp_vecs.append(vec)

        final_vec = tmp_vecs[0]
        for i in range(1, len(tmp_vecs)):
            final_vec = np.concatenate((final_vec, tmp_vecs[i]), axis=0)
        final_kmer2vec_dict[kmer] = final_vec

    # save k-mer embedding
    w2v = gensim.models.keyedvectors.Word2VecKeyedVectors(vector_size=args.dimensions)
    w2v.index_to_key = final_kmer2vec_dict
    w2v.vectors = np.array(list(final_kmer2vec_dict.values()))
    save_word2vec_format(
        binary=True,
        fname='kmer_embedding.bin',
        total_vec=len(final_kmer2vec_dict),
        vocab=w2v.index_to_key,
        vectors=w2v.vectors
    )
    w2v = gensim.models.keyedvectors.Word2VecKeyedVectors.load_word2vec_format('w2v_model.bin', binary=True)
    output_fp = "kmer_embedding.txt"
    w2v.save_word2vec_format(output_fp, binary=False)


if __name__ == "__main__":
    print(os.path.abspath(""))
    cmd_tool = ParameterParser()
    arguments = cmd_tool.parameter_parser()
    main(arguments)