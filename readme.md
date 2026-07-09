나 혼자 개발하고, 내 컴퓨터 코드를 올릴 때 (가장 자주 씀)
git add . 
git commit -m "원하는 설명 적기 (예: 기능 추가)"
git push origin main

GitHub 웹에서 수정했거나 다른 사람이 올린 코드를 가져올 때 
git pull origin main

꿀팁★ 협업하거나 안전하게 작업할 때 (강추 흐름) 
git stash 
git pull origin main 
git stash pop