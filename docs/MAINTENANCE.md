# 支部長等 出走・予定一覧 — 運用手順書

最終更新: 2026-07-16

## 1. このサイトについて

- 公開URL: <https://jpcu-koho.github.io/keirin-officer-schedule/>
- GitHubリポジトリ: `JPCU-KOHO/keirin-officer-schedule`
- 公開方式: GitHub Pages
- 更新方式: GitHub Actions が毎日データを取得し、静的サイトを生成・公開
- 対象: 支部長・支部長代行等の出走状況と参加予定

PCを起動しておく必要はありません。処理はGitHub上で実行されます。

## 2. AIに作業を依頼する場合

CodexなどのAIには、次のように依頼してください。

> このリポジトリの `AGENTS.md` と `docs/MAINTENANCE.md` を読み、公開サイトの変更を実装してください。変更後は構文確認、GitHubへの反映、GitHub Actionsによる公開、公開ページでの確認まで行ってください。

`AGENTS.md` には、AIが守るべき範囲、データ例外、公開方法がまとめられています。通常はこの2ファイルを読ませれば、今回と同じ流れで保守できます。

## 3. 日常の自動更新

`.github/workflows/update-and-deploy.yml` の **Update and deploy schedule** が毎日実行されます。

|項目|設定|
|---|---|
|実行時刻|毎日 05:07（日本時間）|
|cron式|`7 20 * * *`（UTCの前日20:07）|
|データ取得|KEIRIN.JP選手ページとWINTICKET選手ページの予定情報|
|公開先|GitHub Pages|
|公開ブランチ|`main` の最新状態|

05:07にしている理由は、KEIRIN.JPの深夜更新後に余裕を持たせ、GitHub Actionsが混雑しやすい毎時00分を避けるためです。

### 自動更新の流れ

1. 名簿Excelから対象選手を読み込む。
2. 選手ごとに本日の状況と、選手ページに掲載された今後の予定を取得する。
3. Excel監査データとサイト用JSONを生成する。
4. 静的HTMLを生成し、GitHub Pagesへ公開する。

`public/` と `tmp/` はActions内で生成する成果物です。通常はGitへコミットしません。

## 4. GitHubの設定

GitHubの管理画面で設定を見直す際は、以下を維持してください。

|場所|維持する設定|
|---|---|
|Settings → Pages|**Build and deployment: GitHub Actions**|
|Actions タブ|`Update and deploy schedule` が有効|
|Settings → Actions → General|GitHub Actionsの実行を許可。ワークフローが要求する `GITHUB_TOKEN` 権限を制限しない|
|Environment|`github-pages`（Pages公開用。Actionsが使用）|
|リポジトリの公開範囲|公開。URLを知る人が閲覧可能|
|Issues|有効。自動更新失敗の通知Issueに使用|

### ワークフローで必要な権限

ワークフローは、ジョブごとに次の権限を使います。

- `pages: write` と `id-token: write`: GitHub Pagesへの公開
- `contents: write`: 月次ハートビートの記録
- `issues: write`: 更新失敗時のIssue作成・復旧時のIssueクローズ

個人用アクセストークン、外部APIキー、Actions Secretsは現在不要です。新たな秘密情報を追加する場合は、必ずGitHub Secretsに保存し、ソースコードや手順書へ値を書かないでください。

## 5. 60日停止の防止と障害通知

### 60日停止の防止

GitHubは、公開リポジトリに60日間の活動がない場合、スケジュール実行を停止することがあります。そのため `keep_schedule_active` ジョブが約30日ごとに `.github/schedule-heartbeat` を更新して小さなコミットを作ります。

このファイルとジョブを削除しないでください。削除・変更した場合は、定期実行が停止しない代替手段を用意してください。

### 更新失敗時

`build` または `deploy` が失敗すると、GitHub Issue `【自動更新エラー】競輪役員スケジュール` を自動作成します。同じ問題が続く場合は同じIssueに追記されます。次回の更新が正常に完了すると、そのIssueは自動で解決済みになります。

通知メールの受信可否は、担当者のGitHub通知設定に従います。

## 6. 名簿・役職を変更する方法

### 名簿Excelの差し替え

現在の入力ファイルは、リポジトリ直下の次のファイルです。

`支部長・代行・副支部長一覧_20260709.xlsx`

ワークフローにファイル名が固定で書かれています。更新時は次のいずれかを行います。

1. 新しいExcelを同じファイル名で置き換える（推奨）。
2. 新しいファイル名を使う場合は、`.github/workflows/update-and-deploy.yml` の `keirin_status.py` 実行行も同時に変更する。

差し替え後は必ず手動実行で、対象人数・支部名・欠員行を確認してください。

### 常勤役員など、一覧から除外する人を追加・削除

`work/keirin_status.py` の `EXCLUDED_OFFICER_NAMES` を編集します。ここにある名前は取得対象から外れるため、画面変更だけより安全です。

### 役職の表示を個別に変更する

同じく `ROLE_OVERRIDES` に `"氏名": "表示したい役職"` を追加・更新します。

### 大阪支部の支部長行

大阪支部の「支部長」行は、名簿読込時に除外する設定です。再表示する場合は、`extract_players` 内の大阪支部に関する除外条件を見直してください。

## 7. 画面・地区順を変更する方法

|変更内容|編集箇所|
|---|---|
|地区名・都道府県順・支部順|`work/render_static_site.py` の `REGIONS`|
|ステータス名・色|`STATUS` とHTML生成用のJavaScript|
|ヘッダー・注意書き・表の文言|`work/render_static_site.py`|
|対象日選択の判定|`work/render_static_site.py` 内の `plannedState`|

九州の支部順は **福岡 → 佐賀 → 長崎 → 大分 → 熊本 → 鹿児島** です。

対象日選択は、基準日から取得済み予定の最終日まで利用できます。将来日は、予定日程から次のように表示します。

- 開催前日: 前検日
- 開催期間中: 参加予定
- 予定がない日: 予定なし

将来のレース番号・開催区分は推測しません。

## 8. ローカルでの確認

初回のみ依存関係を入れます。

```bash
python3 -m pip install -r requirements.txt
```

構文確認:

```bash
python3 -m py_compile work/keirin_status.py work/export_keirin_status_json.py work/render_static_site.py
```

実データでの生成確認（ネットワーク接続を使用）:

```bash
mkdir -p tmp public/data
python3 work/keirin_status.py "支部長・代行・副支部長一覧_20260709.xlsx" --output tmp/keirin-status.xlsx
python3 work/export_keirin_status_json.py tmp/keirin-status.xlsx --date "$(TZ=Asia/Tokyo date +%F)" --output public/data/keirin-status.json
python3 work/render_static_site.py --data public/data/keirin-status.json --output public/index.html
```

`tmp/` と `public/` の生成物は確認用です。コミット前に `git status` を確認し、意図しない生成物・トークン・個人用ファイルを追加しないでください。

## 9. 変更を公開する手順

1. 対象ファイルだけを編集し、構文確認する。
2. `git diff` と `git status` で差分を確認する。
3. 必要なファイルだけをコミットして `main` へpushする。
4. GitHubの **Actions** → **Update and deploy schedule** → **Run workflow** を実行する。
5. `build`、`deploy`、`resolve-failure-notice` が成功していることを確認する。
6. 公開URLを開き、変更箇所を確認する。

Pagesの配信更新直後は、ブラウザやCDNのキャッシュによって古い画面が短時間残る場合があります。数秒待って再読込し、それでも確認できない場合はクエリ文字列を一時的に付けて開いてください（例: `?v=確認用の文字列`）。

## 10. よくある確認点

- 参加予定は複数サイトの情報を統合しているため、欠場・あっせん変更の反映が遅れることがあります。公開ページの「KEIRIN.JPでの最終確認」注意書きは残してください。
- 「本日の状況」はKEIRIN.JPの情報を優先します。将来予定だけから本日の出走を推測しません。
- 毎朝の更新が失敗した場合は、まず自動作成されたIssueのActionsログを確認します。
- GitHub Actionsの警告に表示されるNode.js実行環境の移行告知は、ジョブ成功時には通常ただちに対応不要です。ただしActionsのメジャーバージョン更新時は公式情報を確認してください。
