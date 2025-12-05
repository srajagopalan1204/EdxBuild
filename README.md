# EdxBuild
this is repo to be used to build the each SOP before passing on to Eduxl2025-SE for unit integration testing and final production roll out 
_++_for quiz and faq
Upload html files for each sop in the respective folders 
then edit one index.html for each 

then follow the steps below 
ensure that you have linked the quiz and faq to the last page of each SOP 


git status

git diff site/BUILD/Quiz/index.html
git diff site/BUILD/FAQ/index.html
git add site/BUILD/Quiz/*.html site/BUILD/FAQ/*.html

git commit -m "Add quiz and FAQ pages and update index links"

git push
_+_+_+_
python "/workspaces/EdxBuild/narr/src/transi_gen_v2.py" \
  --gen poss_merge \
  --sop LineEnt \
  --raw "/workspaces/EdxBuild/narr/Inputs/LineEnt/Raw/LineEnt_Raw_120425_1123.csv" \
  --narr "/workspaces/EdxBuild/narr/Outputs/LineEnt/LineEnt_narr_latest.csv" \
  --out "/workspaces/EdxBuild/narr/Outputs/LineEnt/transi" \
  --thresh 0.72