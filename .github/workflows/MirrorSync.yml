name: 'SyncMirror'

on:
  workflow_dispatch:
  push:

jobs:
  sync:
    runs-on: ubuntu-latest
    steps:
      - name: 'Checkout codes'
        uses: actions/checkout@v2
      
      - name: 'Sync'
        id: commit
        run: |
          git fetch --unshallow
          git checkout master
          git remote add gitea https://${{ secrets.GITEA_USERNAME }}:${{ secrets.GITEA_PASSWORD }}@git.bili33.top/GamerNoTitle/MHYY.git   
          git push gitea master
