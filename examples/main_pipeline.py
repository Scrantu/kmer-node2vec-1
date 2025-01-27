# -*- coding: utf-8 -*-
import sys
sys.path.extend(['.', '..'])
import os
import arrow
import gensim
import networkx as nx
import time
import numpy as np
from gensim.models import KeyedVectors

from util.faiss_getprecision import create_index
from util.faiss_getprecision import precision
from util.perf_tools import Tee

from src.generators import seq2segs
from src.generators import seg2sentence
from src.generators import extract_seg
from src.generators import extract_kmer
from src.generators import parse_seq
from src.generators import save_word2vec_format

from src.kmernode2vec import KMerNode2Vec


class KMerEmbeddings:

    def __init__(
        self,
        p: float,
        q: float,
        mer: int, 
        dimensions: int,  
        workers: int,
        seq_dir: str,
        kmer_vec_output_dir: str,
    ):
        self.p = p
        self.q = q
        self.mer = mer
        self.workers = workers
        self.dimensions = dimensions
        self.seqs = parse_seq([seq_dir])
        self.kmer_vec_output_dir = kmer_vec_output_dir

    def train(self):
        """ Obtain the k-mer embedding. """

        clf = KMerNode2Vec(p=self.p, q=self.q, workers=self.workers)
        clf.fit(
            seqs=self.seqs,
            mer=self.mer,
            path_to_edg_list_file=self.kmer_vec_output_dir + f"networkfile.edg",
            path_to_embeddings_file=self.kmer_vec_output_dir + f"kmer-node2vec-embedding.txt",
        )
        


class SequenceEmbeddings:

    def __init__(
        self,
        mer: int,
        kmer2vec_file: str,
        seq_dir: str,
        segment_length: int,
        segment_number: int,
        segment_file: str,
        extracted_original_segment_file: str,
        extracted_subsegment_file: str,
        sequence_vec_output_dir: str,

    ):
        """ segment embeddings """
        self.mer = mer  
        self.kmer2vec_file = kmer2vec_file
        self.seqs = parse_seq([seq_dir])
        self.seg_vec_output_dir = sequence_vec_output_dir

        # the length and number of segments that we will split
        self.seg_length = segment_length
        self.seg_num = segment_number

        """ These files will be generated by the 'train' function."""
        self.seg_file = segment_file  # segments split from sequences
        # randomly choose 1k segments from seg_file and extract subsegments from the 1k segments
        self.extracted_orgseg_file = extracted_original_segment_file
        self.extracted_subseg_file = extracted_subsegment_file

    def segment_embeddings(self):
        """ Obtain segment embeddings with pre-trained k-mer embeddings. """

        # create segment.txt;
        # note that if an old one exists, we would not overwrite it.
        if not os.path.exists(self.seg_file):
            seq2segs(
                self.seqs,
                self.seg_length,
                self.seg_file,
            )

        with open(self.seg_file, 'r', encoding='utf-8') as fp:
            segs = [line.split('\n')[0] for line in fp.readlines()]
        sentences = seg2sentence(segs, self.mer)  # Tokenize

        from util.vectorizer import AVG
        vecs = KeyedVectors.load_word2vec_format(self.kmer2vec_file)  # k-mer vectors

        clf = AVG(vecs)
        clf.train(sentences)
        clf.save_embs_format(
            self.seg_vec_output_dir,
            f"{'SegmentVectors'}"
        )

    def subseg_embeddings(self):

        # Randomly extract sub-segments from self.seg_file
        if not os.path.exists(self.extracted_orgseg_file) and \
                not os.path.exists(self.extracted_subseg_file):  # prevent overwriting
            extract_seg(
                self.seg_file,
                self.seg_length,
                self.seg_num,
                self.extracted_subseg_file,
                self.extracted_orgseg_file,
            )

        # load subsegments
        with open(self.extracted_subseg_file, 'r', encoding='utf-8') as fp:
            subsegs = [line.split('\n')[0] for line in fp.readlines()]
        sentences = seg2sentence(subsegs, self.mer)

        from util.vectorizer import AVG
        vecs = KeyedVectors.load_word2vec_format(self.kmer2vec_file)  # k-mer2vec file

        clf = AVG(vecs)
        clf.train(sentences)
        clf.save_embs_format(
            self.seg_vec_output_dir,
            f"{'SubSegmentVectors'}"
        )

    def train(self):
        """ Generate four types of files:
            1、One file of segments.
            2、One file of randomly extracted subsegments.
            3、One file of randomly extracted segments from which subsegments originally come.
            4、Six files of vectors corresponding to segments/subsegments. 

        Note:
            Files of segments/subsegments are designed to be fed 
            into sequence retrieval task. See 'class SequenceRetrieval'.
        """
        self.segment_embeddings()
        self.subseg_embeddings()


class SequenceRetrieval:

    def __init__(
        self,
        segment_name_file: str,
        segment_vec_file: str,
        original_subsegment_name_fle: str,
        subsegment_vec_file: str,
        faiss_index_file: str,
        faiss_log: str,
        top_kn: int,
    ):
        """ Note: we use segments from which ramdomly selected subsegments 
            originally come to take the place of subsegments, in order to 
            make comparisons with segments in corpus . """
        self.segment_name_file = segment_name_file
        self.segment_vec_file = segment_vec_file
        self.original_subsegment_name_fle = original_subsegment_name_fle
        self.subsegment_vec_file = subsegment_vec_file

        self.faiss_index_file = faiss_index_file
        self.faiss_log = faiss_log
        self.top_kn = top_kn

    def train(
        self,
        dimension: int,
        index_method: str,
        vertex_connection: int,
        ef_search: int,
        ef_construction: int,
    ):
        """ Print the Top-K result for sequence retrieval task """
        logger = Tee(self.faiss_log)
        sys.stdout = logger

        if create_index(
            self.segment_vec_file,
            self.faiss_index_file,
            dimension,
            index_method,
            vertex_connection,
            ef_search,
            ef_construction,
        ):
            precision(
                self.subsegment_vec_file,
                self.original_subsegment_name_fle,
                self.segment_name_file,
                self.faiss_index_file,
                self.top_kn
            )


def kmer_embeddings(work_dir):
    clf = KMerEmbeddings(
        p=1.0,
        q=0.001,
        mer=8,
        dimensions=[128],
        workers=4,
        seq_dir=work_dir,
        kmer_vec_output_dir=work_dir,
    )
    clf.train()


def sequence_embeddings(work_dir):
    clf = SequenceEmbeddings(
        mer=8,  # consistent with the length k of pre-trained k-mers
        kmer2vec_file=work_dir+f"kmer-node2vec-embedding.txt",  # set this
        seq_dir=work_dir,
        segment_length=8,
        segment_number=10,
        segment_file=work_dir+'segment.txt',
        extracted_original_segment_file=work_dir+'extracted_org_segment.txt',
        extracted_subsegment_file=work_dir+'extracted_sub_segment.txt',
        sequence_vec_output_dir=work_dir,
    )
    clf.train()


def sequence_retrieval(work_dir):
    clf = SequenceRetrieval(
        segment_name_file=work_dir+'segment.txt',
        segment_vec_file=work_dir+'SegmentVectors.txt',  # set this
        original_subsegment_name_fle=work_dir+'extracted_org_segment.txt',
        subsegment_vec_file=work_dir+'SubSegmentVectors.txt',  # set this
        faiss_index_file=work_dir+'faiss-index-file',
        faiss_log=work_dir+'faiss-result.log',
        top_kn=20,
    )
    clf.train(
        dimension=128,  # consistent with dimensionality of sequence embedding
        index_method='HNSW',
        vertex_connection=100,
        ef_search=2000,
        ef_construction=128,
    )


def pipeline():
    """
    Note: 
        Run functions !!!one by one!!!, since the next 
        function's input requires the previous function's output.
        Need to manually modify some file names in each Step.
    """
    start_time = time.time()
    kmer_embeddings(work_dir='../data_dir/input/')  # Step1
    end_time = time.time()
    print('kmer_embedding costs {:.5f} s'.format(end_time - start_time))

    sequence_embeddings(work_dir='../data_dir/input/')  # Step2
    sequence_retrieval(work_dir='../data_dir/input/')  # Step3


if __name__ == '__main__':
    pipeline()
