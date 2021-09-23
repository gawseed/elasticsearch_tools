import sys
import argparse
import pandas as pd
import numpy as np
import pyfsdb
import dnssplitter

splitter = dnssplitter.DNSSplitter()
splitter.init_tree()

def get_psl(x):
    noval = [np.NaN, np.NaN, np.NaN]
    try:
        ret = splitter.search_tree(x)
        if not ret or len(ret) != 3:
            return noval
        return ret
    except:
        return noval

def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("-i", "--infile", help="Input file",
            type=argparse.FileType('r'), action="append", default=None)
    parser.add_argument("-o", "--outfile", help="Output file", type=argparse.FileType('w'), default="-") 
    parser.add_argument("-s", "--sortkey", help="Sort by key", type=str, default=None)
    parser.add_argument("-H", "--addheader", help="Add FSDB header", action="store_true")
    parser.add_argument("-p", "--pslkey", help="Split PSL key", type=str, action="append", default=None)
    parser.add_argument("-M", "--pslmerged", help="Make merged psl columns", action="store_true")
    p = parser.parse_args(argv)

    # create empty dataframe
    df = pd.DataFrame()

    # Process each file and add to dataframe
    for fp in p.infile:
        db = pyfsdb.Fsdb(file_handle=fp)
        rows = [r for r in db]
        data = np.array(rows)
        dfp = pd.DataFrame(data=data, columns=db.column_names)
        df = pd.concat([df,dfp], ignore_index=True)

    cols = list(df.columns)

    # Sort dataframe
    if p.sortkey:
        df.sort_values(by=[p.sortkey], inplace=True)
        # Move sortkey to first col
        if p.sortkey in cols:
            cols.remove(p.sortkey)
            cols.insert(0, p.sortkey)
            df = df[cols]

    # Add psl where needed
    if p.pslkey:
        pslcols = ["_pslpfx", "_psldom", "_pslpub"]
        dfncons = pd.DataFrame(columns=pslcols)
        for k in p.pslkey:
            vals = df[k].apply(lambda x: get_psl(x))
            dfn = vals.to_frame()
            listvals = dfn[k].values.tolist()
            dfn_split = pd.DataFrame(listvals, index=dfn.index, columns=pslcols)
            newcols = [k+c for c in pslcols]
            df[newcols] = dfn_split
            cols.extend(newcols)
            # Create a merged dataframe
            if dfncons.empty:
                dfncons = dfn_split
            else:
                dfncons.update(dfn_split, overwrite=True)
        if p.pslmerged:
            df[pslcols] = dfncons
            cols.extend(pslcols)

    # Write dataframe as fsdb
    if p.addheader:
        #hdrstr = "#fsdb -F C|"
        hdrstr = "#fsdb -F t"
        for h in cols:
            hdrstr += " %s" % (h)
        p.outfile.write(hdrstr + '\n')
    #df = df.replace(r'\\r', '', regex=True)
    #df.to_csv(path_or_buf=p.outfile, sep='|', header=False, index=False)
    df.to_csv(path_or_buf=p.outfile, sep='\t', header=False, index=False)

if __name__ == "__main__":
    main(sys.argv[1:])
