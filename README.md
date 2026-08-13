# project-asie5607

SKNET MonsterTV HDUC / U3（ASIE5607搭載）をLinuxから利用するための、非公式な
user-space実験実装です。公式Windows driverを実行時に使わず、USB初期化、選局、
EP81受信、独自raw形式から標準MPEG-TSへの変換を行います。

現在の実機確認範囲は次のとおりです。

| 機種 | 地上波 | BS/110度CS | 常駐録画 |
|---|---|---|---|
| MonsterTV HDUC (`3275:7080`) | 物理ch13〜62、ch21/ch22等でlive確認 | 非対応 | `hducd` + `recpt1-hduc` |
| MonsterTV U3 (`3275:9010`) | 物理ch13〜62、ch21↔ch22をlive確認 | 全24 transponderを実装、BS13/CS22をlive確認 | `u3d` + `recpt1-u3` |

U3では、同じUSB handleと8本のEP81 URBを維持したまま
地上ch21→BS13→CS22→地上ch21を往復し、標準TSまで変換できることを確認済みです。
BS13は外付けB-CAS後段でscrambled packet 0、CS22ではclearのQVC映像・音声を確認しました。

## 重要：firmwareは同梱していません

このrepositoryはSKNETのfirmware、Windows driver、DLL、installerを配布しません。
利用者が所有する対応機器用の**32-bit版** `SKNET_AS11Loader.sys` を自分で用意し、
ローカルでruntime imageを生成してください。64-bit版loader driverは入力にできません。

対応する版は、**2009年11月10日公開**のHDUC用driver package
`091110_Driver.zip`（Driver Ver.1.9.10.20）に含まれる32-bit版です。
2009年11月27日公開のU3用`091127_Driver_U3.zip`にも、これと同一SHA-256の
`SKNET_AS11Loader.sys`が含まれます。file内部のPE timestampは
2009年9月24日 03:24:08 UTCです。

対応入力のSHA-256：

```text
9abd9c8cd901d36235d96e8361ab51d7b8538bdc39a38a03d4c2d7c1b6ecfbe0
```

本projectはdriverをダウンロードしません。所有機器に付属した媒体、正規に入手した
上記日付のinstaller、または自分のWindows環境から取得してください。

依存package導入後、repository rootで次を実行します。

```bash
python3 scripts/extract_as11loader_firmware.py \
  /path/to/SKNET_AS11Loader.sys
```

次のローカルfileが生成されます。

```text
firmware/as11loader_decrypted_full.bin
SHA-256: f4848c8c091634897f9829e50d2ff8e5dc28792c6b20cf095d38d40379518c7a
```

生成物はGitで無視されます。driverと生成したfirmwareを再配布しないでください。
抽出scriptの提供は、vendor fileの取得・利用・再配布に関する許諾を与えるものでは
ありません。利用者自身の権利と所在地の法令・契約を確認してください。

## 同梱物

- `scripts/extract_as11loader_firmware.py` — 利用者所有driverからのローカル生成器
- `data/hduc-x64-init.json` — nonce/Bulk payloadを除いたHDUC初期化manifest
- `data/hduc-x64-mode6-material.json` — HDUC raw→TS変換材料
- `templates/u3_good2_terrestrial.json` — IN responseを除いたU3 startup template
- `tools/hduc_ctl/` — libusb制御、選局、非同期Bulk受信、keepalive
- `scripts/hducd`, `scripts/recpt1-hduc` — HDUC常駐backend/client
- `scripts/u3d`, `scripts/recpt1-u3` — U3地上波・BS/CS常駐backend/client
- offline検証、TS/PSI/CA検査、one-shot診断scriptとunit test

以下は同梱しません。

- firmware、Windows driver/DLL/application/installer
- PCAP/USBPcap、録画TS、放送内容、driver memory dump
- B-CASの応答・カード番号、ARIB STD-B25実装
- 第三者projectからコピーしたsourceまたはbinary

U3 templateにcaptured IN responseやsmart-card IN dataは含まれません。保持しているcard OUTは
固定のT=1 IFSとB-CAS startup commandのみで、回帰testで内容を監査しています。

## 必要環境とbuild

Ubuntu/Debian系の例：

```bash
sudo apt install build-essential pkg-config libusb-1.0-0-dev \
  python3 python3-venv usbutils
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
make
make test
```

その後、前節の手順でfirmwareを生成してください。USB deviceへアクセスできない場合は、
udev ruleまたはroot権限の調整が別途必要です。

## HDUCを使う

### 常駐backend（推奨）

HDUCを接続し、生成済みfirmwareがある状態でdaemonを起動します。

```bash
scripts/hducd
```

loader状態ならfirmwareを転送し、初期化後も同じUSB handle、EP81 URB、heartbeatを
保持します。`HDUC server ready`後、別terminalからrecpt1形式で録画できます。

```bash
# 物理ch21を30秒
scripts/recpt1-hduc 21 30 /tmp/ch21.ts

# HH:MM:SSとstdout
scripts/recpt1-hduc 21 00:05 - > /tmp/ch21.ts

# Ctrl-Cまで
scripts/recpt1-hduc 21 - - > /tmp/ch21.ts
```

同一channelの連続録画、物理ch13〜62の再選局、全域scan後の復帰を実機確認済みです。
daemonだけを再起動し、HDUC runtimeがまだ生きている場合は初期化を省略できます。

```bash
scripts/hducd --reuse-runtime
```

### one-shot診断

```bash
scripts/run_hduc_x64_live_once.sh --channel 21 --output /tmp/ch21.ts
```

Windows実測と同じ待ち時間を含むため、cold initは約225秒かかります。既定では取得後も
接続を保持し、停止は`Ctrl-C`です。

```bash
HDUC_KEEPALIVE_SECONDS=90 scripts/run_hduc_x64_live_once.sh \
  --channel 21 --output /tmp/ch21.ts

HDUC_KEEPALIVE=0 scripts/run_hduc_x64_live_once.sh \
  --channel 21 --output /tmp/ch21.ts
```

初期化済みruntimeの選局だけを行う場合：

```bash
tools/hduc_ctl/hduc_ctl tune --channel 35
```

## U3を使う

U3本体のB-CAS slotへ通常どおりカードを挿入します。HDUCとU3はloader時のUSB ID
`1738:5211`が共通なので、複数台接続時は物理bus/portを必ず指定してください。

### 常駐backend（推奨）

```bash
scripts/u3d --bus 2 --port 2 --channel 21
```

別terminalから地上波を録画できます。

```bash
scripts/recpt1-u3 21 30 /tmp/u3-ch21.ts
scripts/recpt1-u3 22 30 /tmp/u3-ch22.ts
```

別channel要求時もprimary USB handleとEP81 URBを閉じず、tune/re-armを実行します。
地上ch21↔ch22でPAT/全PMT、CC不連続0、外部B25後scrambled 0を確認済みです。

BSは奇数transponder `BS1..BS23`（任意の`_slot` suffix可）、110度CSは偶数
`CS2..CS24`です。

```bash
# BS13 multiplex（BS日テレservice 141を含む）
scripts/recpt1-u3 BS13_0 30 /tmp/u3-bs13.ts
scripts/recpt1-u3 BS141   30 /tmp/u3-bs13.ts

# CS22 multiplex（clearのQVC service 161を含む）
scripts/recpt1-u3 CS22 30 /tmp/u3-cs22.ts
scripts/recpt1-u3 QVC  30 /tmp/u3-qvc.ts

# 同じdaemonから地上波へ復帰
scripts/recpt1-u3 21 30 /tmp/u3-ch21.ts
```

全24 transponderのcontrolを生成できますが、live確認済みはBS13とCS22です。現状は
multiplex全体を保存し、`--sid`によるservice抽出は行いません。

### one-shot診断

```bash
U3_BUS=2 U3_PORT=2 scripts/run_u3_terrestrial_once.sh \
  --channel 21 --output /tmp/u3-ch21.ts
```

startupはPCAP、Windows driver/DLL、Unicorn、参照録画を実行時に読みません。接続中の
U3からchallengeを読み、独立実装でresponseを計算します。stream graph rowはsessionごとに
変化するため、全16候補からCRC-valid PATを作るrowを自動選択します。

## B-CAS後段

本projectはARIB STD-B25実装を同梱しません。利用者が別途導入したtoolを使う場合：

```bash
HDUC_B25_BIN=/path/to/b25 \
HDUC_B25_OUT=/tmp/ch21-decoded.ts \
scripts/run_hduc_x64_live_once.sh --channel 21 --output /tmp/ch21.ts
```

U3 one-shotでは`U3_B25_BIN`/`U3_B25_OUT`を使用します。録画・復号・視聴は放送契約、
カード利用条件、所在地の法令に従ってください。

## 現在の制限

- DVB device nodeではなくUnix socketを使うuser-space backend
- 各daemonはチューナー1台、同時録画client 1本
- `--sid`、内蔵`--b25`/`--strip`、HTTP/UDP、EPG、録画予約は未実装
- U3衛星のlive確認はBS13/CS22のみ
- HDUC cold initは約225秒。常駐backendでは一度だけ実行
- 長時間HDUC EP81で稀なsideband recordを観測しており、後続は再同期して復帰

## 安全上の注意

- 通常運用でUSB resetを使わないでください。
- 異なる機種やdriver buildのcontrol列をblind replayしないでください。
- `1738:5211`はHDUC/U3共通です。複数台接続時はbus/port指定が必須です。
- このprojectはSKNET、ASICEN、ARIB、放送事業者とは無関係です。

project固有の帰属表示は[NOTICE](NOTICE)、第三者fileとの境界は
[NOTICE.md](NOTICE.md)を参照してください。開発への参加方法は
[CONTRIBUTING.md](CONTRIBUTING.md)にあります。

## License

Copyright 2026 bamboo（GitHub: [b4mbo-o](https://github.com/b4mbo-o)）

このprojectの、copyright holderが許諾する権利を持つsource・document・dataは
[Apache License, Version 2.0](LICENSE)で提供します。商用を含む利用、改変、再配布、
sublicenseが可能です。再配布時はApache-2.0の条件に従い、licenseとcopyright・NOTICEを
保持し、変更したfileには変更の旨を明示してください。

SKNETその他のvendor driver、そこから利用者が生成するfirmware、放送内容、B-CAS data、
第三者softwareにはこのlicenseを付与しません。これらは公開repositoryに含まれていません。
