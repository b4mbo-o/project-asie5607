# 常設運用

## install

Ubuntu/Debianではbuild依存に加え、runtime用のPyUSBとcryptography、B-CASを使う場合は
PC/SCを導入します。

```bash
sudo apt install build-essential pkg-config libusb-1.0-0-dev \
  python3 python3-usb python3-cryptography pcscd
make
make test
sudo make install
sudo make install-firmware \
  FIRMWARE="$PWD/firmware/as11loader_decrypted_full.bin"
```

`install-firmware`は既知のSHA-256と一致する生成物だけを受理します。vendor driverと
firmwareをpackageへ取り込むことはありません。

専用userを一度作成し、接続位置に合わせて`/etc/default/asie5607-u3`または
`asie5607-hduc`のbus/portを編集します。

```bash
sudo useradd --system --no-create-home --user-group asie5607 2>/dev/null || true
sudo usermod -a -G video asie5607
sudo udevadm control --reload-rules
sudo systemctl daemon-reload
sudo systemctl enable --now asie5607-u3.service
journalctl -u asie5607-u3.service -f
```

udev ruleの再読込はUSB resetを行いません。既に接続中のdeviceへ新しいpermissionを適用する
には一度だけ物理再接続するか、次の自然な再列挙を待ちます。

## 自動復旧

`hducd`と`u3d`はworkerがUSB切断、Bulk停止、heartbeat失敗などで終了すると、既定で2秒後に
同じbus/physical portを使って再起動します。loader modeなら既知firmwareを再投入し、
初期化からsocket再作成まで行います。`libusb_reset_device`は使用しません。録画中clientは
切断されるため、呼出側が新しいsocketへ再接続してください。systemdの`Restart=on-failure`は
supervisor自身が異常終了した場合の二重の保護です。

deviceがUSB busの一覧から完全に消えた場合、supervisorは再接続待ちを繰り返します。この状態を
USB control転送だけで復活させることはできないため、物理再接続またはhost/hypervisor側での
再接続が必要です。再接続後は人手でdaemonを再起動する必要はありません。

```bash
# 10秒間隔、最大5回だけ復旧を試す
u3d --retry-seconds 10 --max-restarts 5 --bus 2 --port 2

# 従来どおり一回で終了
u3d --no-recover --bus 2 --port 2
```

## recpt1 option

```bash
# service 141だけを残し、null packetを除去
recpt1-u3 --sid 141 --strip BS13_0 30 bs141.ts

# 利用者が別途導入したrecfriio互換b25をlive pipelineへ接続
recpt1-u3 --b25 --b25-bin /usr/local/bin/b25 --sid 141 --strip \
  BS13_0 30 bs141-clear.ts
```

`--sid`はdecimalまたは`0x`形式をcomma区切りで指定できます。PATを選択serviceだけに再構成し、
対象PMT、PCR、ES、ECMと共通SIを保持します。`--strip`はPID `0x1fff`を除去します。外部B25は
`/dev/stdin`/`/dev/stdout`を受理するrecfriio互換CLIを想定し、repositoryには同梱しません。

## Mirakurun

`examples/mirakurun-tuners.yml`と`mirakurun-channels.yml`を利用中の設定へmergeします。
Mirakurun 4系の`<channel>` command variable形式です。Mirakurun側decoderとclientの
`--b25`を同時には有効にしないでください。daemon socketへMirakurun userが接続できるよう、
同userを`video` groupへ追加します。

Mirakurun 4.1.3 + Node.js 22で、U3 1台を`GR`/`BS`/`CS`兼用tunerとして実機確認済みです。
初回service scanは地上ch21（フジテレビ）、BS13（BS日テレ）、CS22（QVC）を順に検出し、
channel streamとservice streamの両APIから188-byte同期TSを取得できました。外部B25を
tuner commandへ接続した試験では、フジテレビ1056、BS日テレ141、QVC 161の各service
streamがscrambled packet 0でした。

Mirakurunは視聴終了から数秒後にtuner commandへ`SIGTERM`を送ります。`recpt1-hduc`と
`recpt1-u3`はこれを通常の録画中断として処理し、B25 processとdaemon socketを閉じます。
daemon本体とprimary USB handleは終了しないため、次の選局要求にそのまま応答します。
