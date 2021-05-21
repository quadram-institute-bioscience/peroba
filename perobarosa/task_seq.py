#!/usr/bin/env python
from perobarosa.utils_seq import *

logger = logging.getLogger(__name__) # https://github.com/MDU-PHL/arbow
logger.propagate = False
stream_log = logging.StreamHandler()
log_format = logging.Formatter(fmt='peroba_TASK %(asctime)s [%(levelname)s] %(message)s', datefmt="%Y-%m-%d %H:%M")
stream_log.setFormatter(log_format)
stream_log.setLevel(logging.INFO)
logger.addHandler(stream_log)

def align (fastafile, defaults, alignment = None, output = None, length = 20000, ambiguous = 0.1):
    reference = defaults["reference"]
    if output is None: output = defaults["current_dir"] + "incremental." +  defaults["timestamp"] + ".aln.xz"
    if ambiguous is None or ambiguous > 0.9: ambiguous = 0.1
    logger.info (f"Will exclude sequences with proportion of Ns higher than {ambiguous} or shorter than {length}");

    # read existing alignments
    if alignment is None: logger.info (f"No alignment given; will align all sequences from fasta file")
    else:                 logger.info (f"Will read all alignment files and store sequence names")
    aln_seqnames = []
    for aln in alignment:
        logger.debug(f"Reading alignment {aln}") 
        aln_seqnames += read_fasta_headers (aln)
    aln_seqnames = list(set(aln_seqnames))
    logger.info("Reading fasta file %s and store incrementally (i.e. not already aligned)", fastafile)
    sequences = []
    n_short = 0
    with open_anyformat (fastafile, "r") as handle:
        for record in SeqIO.parse(handle, "fasta"):
            this_len = len(record.seq)
            if record.id not in aln_seqnames and this_len > length:
                sequences.append(record)
            if this_len <= length:
                logger.debug (f"Sequence {record.id} too short, has only {this_len} sites")
                n_short += 1
    n_seqs = len(sequences)
    if n_short > 0: logger.warning ("Number of sequences excluded due to short length: {n_short}")
    if not n_seqs: 
        logger.warning ("No new sequences found in %s (empty file or all included in alignments)", fastafile)
        return
    
    logger.info(f"Preparing file chunks with temporary file names (to run uvaia in parallel)") 
    n_chunks = defaults["n_threads"]
    if n_chunks > n_seqs: n_chunks = n_seqs
    chunk_size = n_seqs//n_chunks + 1
    chunk_ids = [i for i in range (0, n_seqs, chunk_size)]
    n_chunks = len (chunk_ids) 
    chunk_file = [defaults["current_dir"] + "prb." + defaults["timestamp"] + '_%04x_' % random.randrange(16**12) + str(i) for i in chunk_ids]

    logger.info(f"Saving new sequences temporarily into {n_chunks} files for concurrent alignment")
    for i in range(n_chunks):
        ifl = f"{chunk_file[i]}.fas.gz"
        with open_anyformat (ifl, "w") as fw: 
            for x in sequences[chunk_ids[i]:chunk_ids[i] + chunk_size]:
                fw.write(str(f">{x.id}\n{x.seq}\n").encode())
    sequences = []

    logger.info(f"Running uvaia concurrently into file chunks")
    from multiprocessing import Pool
    from functools import partial
    with Pool(n_chunks) as p:
        p.map(partial(run_pu, ambiguous=ambiguous, reference=reference), chunk_file)

    logger.info(f"Merging file chunks into single file")
    for ifl in chunk_file:
        with open_anyformat (f"{ifl}.aln", "r") as fw: 
            for record in SeqIO.parse(fw, "fasta"):
                sequences.append(record)
    runstr = "rm " + " ".join([f"{x}.aln" for x in chunk_file])
    logger.info(f"Deleting chunk files")
    proc_run = subprocess.check_output(runstr, shell=True, universal_newlines=True)
    
    if not len(sequences): 
        logger.warning ("No new aligned sequences, all remaining sequences probably failed length or ambiguous QC)")
        return

    logger.info(f"Saving aligned sequences to {output}")
    with open_anyformat (output, "w") as fw: 
        for x in sequences:
            fw.write(str(f">{x.id}\n{x.seq}\n").encode())

def run_pu (fl, ambiguous, reference):
    runstr = f"uvaialign -a {ambiguous} -r {reference} {fl}.fas.gz > {fl}.aln" 
    proc_run = subprocess.check_output(runstr, shell=True, universal_newlines=True)
    runstr = f"rm {fl}.fas.gz" 
    proc_run = subprocess.check_output(runstr, shell=True, universal_newlines=True)
    return
