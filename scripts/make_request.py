import argparse
from pathlib import Path
from scripts.evaluate import dump
from src.scenarios import scenario,LABELS
if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--scenario",choices=list(LABELS),default="normal");p.add_argument("--directory",default="runtime/request")
    args=p.parse_args();s=scenario(args.scenario);folder=Path(args.directory)
    dump(folder/"input.json",s["request"]);dump(folder/"catalog.json",s["catalog"])
    print(f"Created {folder}/input.json and catalog.json")
