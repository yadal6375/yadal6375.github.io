# あそびば

ちいさなブラウザゲームの置き場。

- **[むすぶ](https://yadal6375.github.io/asobiba/musubu/)** — 図形を回して線の端をすべてつなぐパズル
- **[くみたてる](https://yadal6375.github.io/asobiba/kumitateru/)** — 部品を並べて漢字を組み立てるパズル

## くみたてる

部品を台にドラッグして並べ、漢字を組み立てます。木と木で林、林と木で森。
組み上げた字は、次からその人の部品になります。

- 常用漢字 **2136字**。うち **1898字** が組み立てられます（残る238字は部品そのもので、分解できません）
- 部品は **717種**。素の部品（作れないもの）は396種で、1字つくるごとに1つずつ増えます
- 判定は**部品の集合で候補を絞り、置き方のずれで決めます**。手を止めて1秒たつと走ります
- 進行は localStorage に保存されます

連想や語呂合わせではなく、KanjiVG に記録された**実際の字形構造**をそのまま遊びにしています。
だから組み上がるたびに「へえ」が残ります。

### データの作りかた

```
git clone --depth 1 https://github.com/KanjiVG/kanjivg.git
curl -sSLo data/joyo.tsv https://raw.githubusercontent.com/hiroshi-manabe/Joyo-Kanji-List/master/joyo.tsv

python3 tools/extract.py --verify                              # 外接矩形の検算
python3 tools/extract.py --survey                              # 部品の粒度を比べる
python3 tools/extract.py --min-strokes 2 --out data/kumitateru.json
node tools/judge-test.mjs 13 0.15                              # 判定の検証
```

`kanjivg/`（90MB）と `data/joyo.tsv` はこのリポジトリには含みません。上のコマンドで取得してください。

### 判定の設定

`kumitateru/index.html` の先頭 `CFG` で調整できます。

| 項目 | 値 | 意味 |
|---|---|---|
| `OK` | 13 | この誤差以下ならその字と認める |
| `WS` | 0.15 | 大きさのずれの重み。位置より軽く見る |
| `SETTLE` | 1000 | 手が止まってから判定するまで（ミリ秒） |
| `START` | 10 | 最初に持っている素の部品の数 |
| `PER_FIND` | 1 | 1字つくるごとに増える素の部品の数 |

現在の設定での実測（全1898字）:

| 状況 | 結果 |
|---|---|
| 正解どおりに置く | 1898/1898 通る（最大誤差 8.3） |
| ±8 ずらす | 96.2% 通る |
| ±18 ずらす | 15.9% 通る |
| でたらめに置く | 0.05% しか通らない |
| 部品が同じでぶつかる9組 | 取り違え 0 |

## ライセンス

- **くみたてる** — CC BY-SA 3.0（[kumitateru/LICENSE](kumitateru/LICENSE)）。
  字形データに [KanjiVG](http://kanjivg.tagaini.net)（CC BY-SA 3.0）を使っているため、継承条件により同じライセンスで公開しています
- **むすぶ** — MIT
