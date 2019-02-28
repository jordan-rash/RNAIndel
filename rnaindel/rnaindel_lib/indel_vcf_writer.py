#!/usr/bin/env python3
"""
9th step (last) of analysis

Output analysis result in .vcf
 
'indel_vcf_writer' is the main routine in this module

Must hard-code define_info_dict and define_format_dict
to edit the meta info.
"""

import os
import re
import pysam
import datetime
import pandas as pd
from functools import partial
from .indel_vcf import IndelVcfReport
from .left_aligner import peek_left_base
from .indel_rescuer import sort_positionally
from .indel_classifier import make_feature_dict

metaID = re.compile(r"ID=([A-Za-z]+)")


def indel_vcf_writer(
    df, df_filtered, bam, fasta, chr_prefixed, vcfname, model_dir, version
):
    """Output result in .vcf
    
    Args:
        df (pandas.DataFrame): assumed to be sorted and left-aligned
        bam (str): path to bam
        fasta (str): path to fasta
        chr_prefixed (bool): True if chromosome names are "chr"-prefixed
        vcfname (str): output vcf name
        version (str): RNAIndel's version
    Returns:
        None: a vcf file will be written out
    """
    fa = pysam.FastaFile(fasta)

    if not df_filtered.empty:
        df = pd.concat([df, df_filtered], axis=0, ignore_index=True, sort=True)

    df = sort_positionally(df)

    info = define_info_dict()
    fmt = define_format_dict()
    vcf = partial(
        generate_indel_vcf,
        info_dict=info,
        format_dict=fmt,
        fa=fa,
        chr_prefixed=chr_prefixed,
    )

    df["vcf"] = df.apply(vcf, axis=1)
    vcf_records = df.apply(lambda x: x["vcf"].vcf_record, axis=1).values

    with open(vcfname, "w") as f:
        f.write(vcf_template(bam, fasta, info, fmt, model_dir, version) + "\n")
        f.write("\n".join(vcf_records))


def generate_indel_vcf(row, info_dict, format_dict, fa, chr_prefixed):
    """Converts Bambino format to VCF format and 
    populate meta info

    Args:
        row (pandas.Series): each row represents an indel
        info_dict (dict): generated by define_info_dict()
        format_dict (dict): generated by define_format_dict()
        fa (pysam.FastFile): obj. storing the refernce info
        chr_prefixed (bool): True if chromosome names are "chr"-prefixed
    Returns:
        idl_vcf (IndelVcfReport obj.)
    """
    idl_vcf = IndelVcfReport(
        fa, row["chr"], row["pos"], row["ref"], row["alt"], chr_prefixed
    )

    # dbSNP ID
    if row["dbsnp"] == row["dbsnp"]:
        idl_vcf.ID = row["dbsnp"]
    else:
        idl_vcf.ID = None

    # FILTER
    idl_vcf.FILTER = row["filtered"]

    # fill INFO field
    info = link_datadict_to_dataframe(row, info_dict)
    idl_vcf.INFO = info

    # fill FORMAT field
    format = link_datadict_to_dataframe(row, format_dict)
    idl_vcf.FORMAT = format

    return idl_vcf


def link_datadict_to_dataframe(row, dict):
    """Match column name and acutal data in dataframe
    
    Args:
        row (pandas.Series)
        dict (dict): info_dict or format_dict
    Returns:
        d (dict): {'meta_info_ID: row['column_name']}
    """
    d = {}
    for k, v in dict.items():
        d[k] = [row[c] if row[c] == row[c] else None for c in v["COLUMN"]]

        if len(d[k]) == 1:
            d[k] = d[k][0]
        elif None in d[k]:
            d[k] = None

    return d


def get_today():
    """Get today's date

    Args:
        None
    Returns:
        today (str): yyyymmdd
    """
    dt = datetime.datetime.now()
    today = str(dt.year) + str(dt.month) + str(dt.day)

    return today


def get_samplename(bam):
    """Get sample name

    Args:
        bam (str): path to bam
    Returns:
        samplename (str): as found in bam file
                          or 'SampleName' if not found
    """
    try:
        bamheader = pysam.AlignmentFile(bam).header
        samplename = bamheader["RG"][0]["SM"]
    except:
        samplename = "SampleName"

    return samplename


def vcf_template(bam, fasta, info_dict, format_dict, model_dir, version):
    """Prepare VCF meta info lines and header lines 
    https://samtools.github.io/hts-specs/VCFv4.2.pdf
  
    Args:
       bam (str): path to bam
       info_dict (dict): generated by define_info_dict()
       format_dict (dict): generated by define_format_dict()
       version (str): RNAIndel's version
    Returns:
       template (str): representing VCF template
    """
    meta_1 = [
        "##fileformat=VCFv4.2",
        "##filedate=" + get_today(),
        "##source=RNAIndelv" + version,
        "##reference=" + fasta,
        '##FILTER=<ID=NtF,Description="Not found as specified in the input VCF">',
        '##FILTER=<ID=Lt2,Description="Less than 2 ALT allele count">',
        '##FILTER=<ID=RqN,Description="Rescued with nearest indel">',
    ]

    info_order = [
        "PRED",
        "PROB",
        "ANNO",
        "MAXMAF",
        "COMMON",
        "CLIN",
        "REP",
        "LC",
        "LLC",
        "GC",
        "LGC",
        "SG",
        "LSG",
        "DSM",
        "ICP",
        "ISZ",
        "INS",
        "ATI",
        "ATD",
        "GCI",
        "GCD",
        "REFC",
        "ALTC",
        "BID",
        "UQM",
        "NEB",
        "EQX",
        "MTA",
        "FRM",
        "SPL",
        "TRC",
        "CDD",
        "LOC",
        "NMD",
        "IPG",
        "LEN",
        "DBSNP",
        "RCF",
        "RQB",
    ]

    meta_2 = [
        "##INFO=<ID=" + i + ","
        "Number=" + info_dict[i]["Number"] + ","
        "Type=" + info_dict[i]["Type"] + ","
        'Description="' + info_dict[i]["Description"] + '">'
        for i in info_order
    ]

    format_order = ["AD"]

    meta_3 = [
        "##FORMAT=<ID=" + i + ","
        "Number=" + format_dict[i]["Number"] + ","
        "Type=" + format_dict[i]["Type"] + ","
        'Description="' + format_dict[i]["Description"] + '">'
        for i in format_order
    ]

    meta_4 = [k + "=" + v for k, v in format_used_features(model_dir).items()]

    meta = meta_1 + meta_2 + meta_3 + meta_4

    header = [
        "#CHROM",
        "POS",
        "ID",
        "REF",
        "ALT",
        "QUAL",
        "FILTER",
        "INFO",
        "FORMAT",
        get_samplename(bam),
    ]

    template = "\n".join(meta + ["\t".join(header)])

    return template


def format_used_features(model_dir):
    """Make header lines for features 
    used for prediction

    Args:
        model_dir (str): path to dir wher "features.txt" is located
    Returns:
        d (dict): {VCF header line: features}
    """
    feature_keys = {
        "indel_complexity": "ICP",
        "dissimilarity": "DSM",
        "indel_size": "ISZ",
        "repeat": "REP",
        "is_uniq_mapped": "UQM",
        "is_near_boundary": "NEB",
        "equivalence_exists": "EQX",
        "is_bidirectional": "BID",
        "is_multiallelic": "MTA",
        "is_inframe": "FRM",
        "is_splice": "SPL",
        "is_truncating": "TRC",
        "is_in_cdd": "CDD",
        "indel_location": "LOC",
        "is_nmd_insensitive": "NMD",
        "ipg": "IPG",
        "coding_sequence_length": "LEN",
        "lc": "LC",
        "local_lc": "LLC",
        "gc": "GC",
        "local_gc": "LGC",
        "strength": "SG",
        "local_strength": "LSG",
        "is_ins": "INS",
        "is_at_ins": "ATI",
        "is_at_del": "ATD",
        "is_gc_ins": "GCI",
        "is_gc_del": "GCD",
        "ref_count": "REFC",
        "alt_count": "ALTC",
        "is_on_dbsnp": "DBSNP",
    }

    feature_dict = make_feature_dict(model_dir)

    features_used_for_sni = [
        feature_keys[f] for f in feature_dict["single_nucleotide_indels"]
    ]
    features_used_for_mni = [
        feature_keys[f] for f in feature_dict["multi_nucleotide_indels"]
    ]
    features_used_for_sni.sort()
    features_used_for_mni.sort()

    d = {}
    d["##features_used_for_1-nt_indels"] = ";".join(features_used_for_sni)
    d["##features_used_for_>1-nt_indels"] = ";".join(features_used_for_mni)

    return d


def define_info_dict():
    """Define INFO field in dict

    Args:
      None
    Returns:  
       d (dict): dict of dict. The first dict's key is 
                 INFO ID (see VCF spec.). The value of 
                 'COLUMN' in the nested dict is a list.
       
                d=  {
                     'INFO_ID'{
                               'COLUMN':['column name in df']
                               'Number':'see VCF spec'
                               'Type':'see VCF spec'
                               'Description':'describe this INFO'
                              },
                     'INFO_ID'{
                                ....
                              }
                    }
    """

    d = {
        "PRED": {
            "COLUMN": ["predicted_class"],
            "Number": "1",
            "Type": "String",
            "Description": "Predicted class: somatic, germline, artifact",
        },
        "PROB": {
            "COLUMN": ["prob_s", "prob_g", "prob_a"],
            "Number": "3",
            "Type": "Float",
            "Description": "Prediction probability of "
            "being somatic, germline, artifact in this order",
        },
        "DBSNP": {
            "COLUMN": ["is_on_dbsnp"],
            "Number": "0",
            "Type": "Flag",
            "Description": "Flagged if on dbSNP",
        },
        "ANNO": {
            "COLUMN": ["annotation"],
            "Number": ".",
            "Type": "String",
            "Description": "Indel annotation in "
            "GeneSymbol|RefSeqAccession|CodonPos|IndelEffect. "
            "Delimited by comma for multiple isoforms",
        },
        "MAXMAF": {
            "COLUMN": ["max_maf"],
            "Number": "1",
            "Type": "Float",
            "Description": "Maximum minor allele frequency (MAF) "
            "reported in dbSNP or ClinVar",
        },
        "COMMON": {
            "COLUMN": ["is_common"],
            "Number": "0",
            "Type": "Flag",
            "Description": "Flagged if curated Common on dbSNP or MAXMAF > 0.01",
        },
        "CLIN": {
            "COLUMN": ["clin_info"],
            "Number": "1",
            "Type": "String",
            "Description": "Clinical Significance|Condition curated in ClinVar",
        },
        "ICP": {
            "COLUMN": ["indel_complexity"],
            "Number": "1",
            "Type": "Integer",
            "Description": "Indel complexity",
        },
        "DSM": {
            "COLUMN": ["dissimilarity"],
            "Number": "1",
            "Type": "Float",
            "Description": "Dissimilarity",
        },
        "ISZ": {
            "COLUMN": ["indel_size"],
            "Number": "1",
            "Type": "Integer",
            "Description": "Indel size",
        },
        "REP": {
            "COLUMN": ["repeat"],
            "Number": "1",
            "Type": "Integer",
            "Description": "Repeat",
        },
        "UQM": {
            "COLUMN": ["is_uniq_mapped"],
            "Number": "0",
            "Type": "Flag",
            "Description": "Flagged if supported by uniquely mapped reads",
        },
        "NEB": {
            "COLUMN": ["is_near_boundary"],
            "Number": "0",
            "Type": "Flag",
            "Description": "Flagged if near exon boundary",
        },
        "EQX": {
            "COLUMN": ["equivalence_exists"],
            "Number": "0",
            "Type": "Flag",
            "Description": "Flagged if equivalent alignments exist for the indel",
        },
        "BID": {
            "COLUMN": ["is_bidirectional"],
            "Number": "0",
            "Type": "Flag",
            "Description": "Flagged if supported by forward and reverse reads",
        },
        "MTA": {
            "COLUMN": ["is_multiallelic"],
            "Number": "0",
            "Type": "Flag",
            "Description": "Flagged if multialleleic",
        },
        "FRM": {
            "COLUMN": ["is_inframe"],
            "Number": "0",
            "Type": "Flag",
            "Description": "Flagged if inframe indel",
        },
        "SPL": {
            "COLUMN": ["is_splice"],
            "Number": "0",
            "Type": "Flag",
            "Description": "Flagged if occurred in splice region",
        },
        "TRC": {
            "COLUMN": ["is_truncating"],
            "Number": "0",
            "Type": "Flag",
            "Description": "Flagged if truncating indel",
        },
        "CDD": {
            "COLUMN": ["is_in_cdd"],
            "Number": "0",
            "Type": "Flag",
            "Description": "Flagged if ocurred in conserved domain",
        },
        "LOC": {
            "COLUMN": ["indel_location"],
            "Number": "1",
            "Type": "Float",
            "Description": "relatice indel location within the transcript coding region",
        },
        "NMD": {
            "COLUMN": ["is_nmd_insensitive"],
            "Number": "0",
            "Type": "Flag",
            "Description": "Flagged if insensitive to nonsense mediated decay",
        },
        "IPG": {
            "COLUMN": ["ipg"],
            "Number": "1",
            "Type": "Float",
            "Description": "Indels per gene",
        },
        "LEN": {
            "COLUMN": ["cds_length"],
            "Number": "1",
            "Type": "Float",
            "Description": "Coding sequence length. Median value if multiple isoforms exist",
        },
        "LC": {
            "COLUMN": ["lc"],
            "Number": "1",
            "Type": "Float",
            "Description": "Linguistic complexity of nucleotide sequence",
        },
        "LLC": {
            "COLUMN": ["local_lc"],
            "Number": "1",
            "Type": "Float",
            "Description": "Local linguistic complexity of nucleotide sequence",
        },
        "GC": {
            "COLUMN": ["gc"],
            "Number": "1",
            "Type": "Float",
            "Description": "GC-content of nucleotide sequence",
        },
        "LGC": {
            "COLUMN": ["local_gc"],
            "Number": "1",
            "Type": "Float",
            "Description": "Local GC-content of nucleotide sequence",
        },
        "SG": {
            "COLUMN": ["strength"],
            "Number": "1",
            "Type": "Float",
            "Description": "Strength of nucleotide sequence",
        },
        "LSG": {
            "COLUMN": ["local_strength"],
            "Number": "1",
            "Type": "Float",
            "Description": "Local strength of nucleotide sequence",
        },
        "INS": {
            "COLUMN": ["is_ins"],
            "Number": "0",
            "Type": "Flag",
            "Description": "Flagged if insertion",
        },
        "ATI": {
            "COLUMN": ["is_at_ins"],
            "Number": "0",
            "Type": "Flag",
            "Description": "Flagged if a signle insertion of A or T",
        },
        "ATD": {
            "COLUMN": ["is_at_del"],
            "Number": "0",
            "Type": "Flag",
            "Description": "Flagged if a single deletion of A or T",
        },
        "GCI": {
            "COLUMN": ["is_gc_ins"],
            "Number": "0",
            "Type": "Flag",
            "Description": "Flagged if a single insertion of G or C",
        },
        "GCD": {
            "COLUMN": ["is_gc_del"],
            "Number": "0",
            "Type": "Flag",
            "Description": "Flagged if a single deletion of G or C",
        },
        "ALTC": {
            "COLUMN": ["alt_count"],
            "Number": "1",
            "Type": "Integer",
            "Description": "The number of unique reads supporting ALT allele",
        },
        "REFC": {
            "COLUMN": ["ref_count"],
            "Number": "1",
            "Type": "Integer",
            "Description": "The number of unique reads supporting REF allele",
        },
        "RCF": {
            "COLUMN": ["reclassified"],
            "Number": "0",
            "Type": "Flag",
            "Description": "Flagged if reclassified",
        },
        "RQB": {
            "COLUMN": ["filtered", "rescued"],
            "Number": "1",
            "Type": "String",
            "Description": "Rescued by indel nearest to this entry",
        },
    }

    return d


def define_format_dict():
    """Define FORMAT field
    Args: 
        None
    Returns:
        d (dict): see define_info_dict 
    """
    d = {
        "AD": {
            "COLUMN": ["ref_count", "alt_count"],
            "Number": "R",
            "Type": "Integer",
            "Description": "Allelic depths by fragment (not read) "
            "for the ref and alt alleles in the order listed",
        }
    }

    return d
