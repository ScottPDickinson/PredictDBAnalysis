#! /usr/bin/env python
__author__ = 'heroico'

import json
import os
import shutil
from subprocess import call

from person import People
from gene import GeneDataSets
import predict_db_input
import geuvadis_input
import gencode_input
import project_utils

#
def split_list(alist, wanted_parts=1):
    """Split an array into -wanted_parts- subarrays"""
    length = len(alist)
    return [ alist[i*length // wanted_parts: (i+1)*length // wanted_parts]
             for i in range(wanted_parts) ]

class Process(object):
    def __init__(self):
        self.gencode_path = None
        self.pheno_path = None
        self.working_folder = None
        self.dbs_path = None
        self.dosages_path = None
        self.predict_db_rsid = None
        self.keep_predictions = None
        self.comparison_plot_path = None
        self.predict_db_rsid = None
        self.eager_clean_up = None

    def eagerCleanUpIfNecessary(self):
        if self.eager_clean_up:
            print "Eagerly cleaning up " + self.working_folder + " and " + self.comparison_plot_path
            shutil.rmtree(self.working_folder)
            shutil.rmtree(self.comparison_plot_path)

    def loadObservedData(self):
        print "Loading gencode"
        self.gencodes = gencode_input.GenCodeSet.LoadGTF(self.gencode_path)
        print "Loading observed data"
        self.observed_data = None
        self.missing_gencodes = None
        self.observed_data,  self.missing_gencodes = geuvadis_input.LoadGEUVADISFile(self.gencodes, self.pheno_path, "observed_geuvadis_genquant")
        print "Loading people"
        self.predict_db_people = People.loadPeopleFromPDBSampleFile(self.dosages_path+"/samples.txt")

    def predictDBForFileIfNecessary(self,file_name):
        output_file_name = self.buildPredictDBOutputFileName(file_name)
        if os.path.isfile(output_file_name):
            print "predict db output %s already exists, delete it if you want it fiugred out again " % (output_file_name, )
            return
        self.predictDBForFile(file_name)

    def predictDBForFile(self, file_name):
        command = self.buildPredictDBCommand(file_name)
        call(command.split(" "))

    def buildPredictDBOutputFileName(self,file_name):
        output_file_name = self.working_folder + "/" + file_name + ".txt"
        return output_file_name

    def buildPredictDBInputFileName(self,file_name):
        input_file_name = self.dbs_path + "/" + file_name + ".db"
        return input_file_name

    def buildPredictDBCommand(self,file_name):
        weight_path = self.buildPredictDBInputFileName(file_name)
        if not os.path.exists(weight_path):
            raise Exception("Database %s does not exist" % (weight_path, ))
        command = "python predict_gene_expression.py "
        command += "--dosages " + self.dosages_path + "/ "
        command += "--weights " + weight_path + " "
        if self.predict_db_rsid is not None:
            command += "--id_col "+self.predict_db_rsid + " "
        command += "--out " + self.buildPredictDBOutputFileName(file_name)
        return command

    def buildQQR2Comparison(self,file_name):
        out = self.buildQQR2ComparisonOutputFileName(file_name)
        print "Starting "+out
        if os.path.isfile(out):
            print "qqr2 already done for "+file_name
            return out
        else:
            print "qqr2 needs doing for "+file_name+ " at "+out
        matching_predict_db_name, matching_observed_name = self.buildComparisonFiles(file_name)
        self.qqR2Compare(file_name, matching_predict_db_name, matching_observed_name)
        return out

    def qqR2Compare(self,file_name, matching_predict_db_name, matching_observed_name):
        print "Calculating qqR2"
        out = self.buildQQR2ComparisonOutputFileName(file_name)
        command = "Rscript comparison_qqR2.R "
        command += "--file1 " + matching_predict_db_name + " "
        command += "--file2 " + matching_observed_name + " "
        command += "--name "+file_name+" "
        command += "--out "+ out
        command = command.encode("ascii","ignore")
        command = command.replace("\\(", "(")
        command = command.replace("\\)", ")")
        call(command.split(" "))
        os.remove(matching_predict_db_name)
        os.remove(matching_observed_name)

    def buildComparisonFiles(self,file_name):
        print "Comparing files for"+file_name
        predict_db_file = self.buildPredictDBOutputFileName(file_name)

        if not os.path.isfile(predict_db_file):
            print "missing predict db output, calculating for "+file_name
            self.predictDBForFile(file_name)
        predict_db_data = GeneDataSets.LoadGeneSetsFromPDBFile(self.predict_db_people, predict_db_file, "predict_db_"+file_name)
        if not self.keep_predictions:
            os.remove(predict_db_file)

        matching_predict_db, matching_observed = GeneDataSets.matchingSets(predict_db_data, self.observed_data)
        matching_predict_db_name = self.buildComparisonOutputFileName(matching_predict_db.name)
        matching_predict_db.dumpCSVWithName(matching_predict_db_name)

        matching_observed_name = self.buildComparisonOutputFileName(matching_observed.name)
        matching_observed.dumpCSVWithName(matching_observed_name)
        return matching_predict_db_name, matching_observed_name

    def buildComparisonOutputFileName(self,file_name):
        name = self.working_folder + "/" + file_name + ".csv"
        return name

    def buildQQR2ComparisonOutputFileName(self,file_name):
        out = self.buildComparisonOutputFileName(file_name+"_correlation")
        return out

    def buildComparisonFileListName(self):
        file_list_name = self.working_folder + "/" + "comparison_file_list.txt"
        return file_list_name

    def plotComparison(self):
        print "Plotting..."
        project_utils.ensure_folder_path(self.comparison_plot_path+"/")
        command = "Rscript plot_qqR2_results.R "
        command += "--result_list_file " + self.buildComparisonFileListName() + " "
        command += "--output_prefix " + self.comparison_plot_path
        call(command.split(" "))

#
class BatchProcess(Process):
    def __init__(self, json_file):
        super(BatchProcess, self).__init__()
        with open(json_file) as data_file:
            json_data = json.load(data_file)

            input = json_data["input"]

            self.eager_clean_up = input["eager_clean_up"]

            self.gencode_path = input["gencode"]
            self.pheno_path = input["pheno"]

            data = input["data"]

            dbs = data["dbs"]
            self.dbs_path = dbs["path"]
            self.dbs_ignore = dbs["ignore"]
            self.keep_predictions = dbs["keep_all"]
            self.predict_db_rsid = dbs["predict_db_col_rsid"] if "predict_db_col_rsid" in dbs else None

            dosages = data["dosages"]
            self.dosages_path = dosages["path"]

            run = json_data["run"]
            self.working_folder = run["working_folder"]

            results = json_data["results"]
            comparison = results["comparison"]
            self.comparison_plot_path = comparison["output_path"]

    def run(self):
        """High level driver"""
        self.eagerCleanUpIfNecessary()
        self.loadObservedData()
        output_files = self.processPredicted()
        self.plotComparison()
        self.plotComparisonMosaic(output_files)

    def processPredicted(self):
        if self.keep_predictions:
            self.predictDBSIfNecessary()
        file_list_name = self.comparePredictedToObserved()
        return file_list_name

    def comparePredictedToObserved(self):
        contents = self.filteredContents(self.dbs_path, self.dbs_ignore)
        file_names = [x.split(".db")[0] for x in contents]

        output_files = []
        for file_name in file_names:
            output_file_name = self.buildQQR2Comparison(file_name)
            output_files.append(output_file_name)

        file_list_name = self.buildComparisonFileListName()
        with open(file_list_name, "w+") as file:
            for output_file_name in output_files:
                line = output_file_name+"\n"
                file.write(line)
        return output_files

    def predictDBSIfNecessary(self):
        contents = self.filteredContents(self.dbs_path, self.dbs_ignore)
        file_names = [x.split(".db")[0] for x in contents]
        for file_name in file_names:
            self.predictDBForFileIfNecessary(file_name)

    def filteredContents(self,path,patterns =[]):
        contents = os.listdir(path)
        filtered_contents = []
        for file in contents:
            is_excluded = False
            for pattern in patterns:
                if pattern in file:
                    is_excluded = True
                    break
            if not is_excluded:
                filtered_contents.append(file)
        return filtered_contents

    def plotComparisonMosaic(self, output_files):
        if len(output_files) == 0:
            return
        parts =round(len(output_files)/9.0)+1
        splitted = split_list(output_files, int(parts))
        for i,split in enumerate(splitted):
            output = self.comparison_plot_path + "/mosaic"+str(i)+".png"
            command = "Rscript plot_qqR2_mosaic.R --results_files "
            command += " ".join(split) + " "
            command += "--output "+output
            call(command.split(" "))
            print command

class BasicProcess(Process):
    def __init__(self, arguments):
        super(BasicProcess, self).__init__()
        db_folders, db_name = os.path.split(arguments.input_db)
        self.dbs_path = db_folders
        self.db_name = db_name.split(".db")[0] if ".db" in db_name else db_name
        self.dosages_path = arguments.dosages_folder
        self.pheno_path = arguments.pheno_file
        self.gencode_path = arguments.gencode_file
        self.working_folder = arguments.working_folder
        self.comparison_plot_path = arguments.results_folder
        self.predict_db_rsid = arguments.predict_db_rsid
        self.keep_predictions = arguments.keep_predictions
        self.eager_clean_up = arguments.eager_clean_up

    def run(self):
        self.eagerCleanUpIfNecessary()
        self.loadObservedData()
        self.predictDBForFileIfNecessary(self.db_name)
        self.comparePredictedtoObserved()
        self.plotComparison()

    def comparePredictedtoObserved(self):
        output_file_name = self.buildQQR2Comparison(self.db_name)

        file_list_name = self.buildComparisonFileListName()
        with open(file_list_name, "w+") as file:
            line = output_file_name+"\n"
            file.write(line)

#
if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description='Compare a series of predicted values against an observeded geuvadis data file.')

    parser.add_argument("--config_file",
                        help="json input file name. If you provide this parameter, config parameters will be loaded from jason, and the script will run over a batch of dbs.",
                        default=None)

    parser.add_argument("--dosages_folder",
                        help="Folder containing -dosage data- in 'PrediXcan format'",
                        default="data/dosagefiles-hapmap2")

    parser.add_argument("--input_db",
                        help="Model DB file to analyse. Assumed to have '.db' extension.",
                        default="data/dbs/cross-tissue_0.5.db")

    parser.add_argument("--pheno_file",
                        help="Phenotype source type",
                        default="data/pheno/GD462.GeneQuantRPKM.50FN.samplename.resk10.txt")

    parser.add_argument("--gencode_file",
                        help="Gencode data file",
                        default="data/gencode.v22.annotation.gtf")

    parser.add_argument("--working_folder",
                        help="Folder where temporary data will be saved to.",
                        default="working_folder")

    parser.add_argument("--results_folder",
                        help="Folder where result statistics will be saved",
                        default="results_folder")

    parser.add_argument("--predict_db_rsid",
                        help="Predict db rsid column name",
                        default="rsid")

    parser.add_argument("--keep_predictions",
                    help="Keep derived predicted gene expression",
                    action="store_true",
                    default=False)

    parser.add_argument("--eager_clean_up",
                    help="Delete working and results folder before starting",
                    action="store_true",
                    default=False)

    args = parser.parse_args()
    if args.config_file:
        print "Starting batch process"
        process = BatchProcess(args.config_file)
    else:
        process = BasicProcess(args)

    process.run()