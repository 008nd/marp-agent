# 本番デプロイ問題整理

## 前提条件

### AgentCore Runtime の制約
- Bedrock AgentCore Runtime は **ARM64 のみ対応**
- Docker イメージは `--platform=linux/arm64` でビルドする必要がある

### CDK Hotswap の制約
- CDK Hotswap（高速デプロイ）を利用するには `AgentRuntimeArtifact.fromAsset()` を使用する必要がある
- `deploy-time-build` は Hotswap 非対応のため使用できない
- `fromAsset()` は**ビルド環境で Docker イメージをビルド**する

### Amplify Console の制約
- Amplify Console のビルド環境は **x86_64 のみ対応**
- カスタムビルドイメージも x86_64 のみサポート
- ARM64 イメージ（`amazonlinux-aarch64-standard:3.0`）を指定するとコンテナが起動しない

## 問題

上記の前提条件により、**Amplify Console で ARM64 Docker イメージをビルドできない**。

```
AgentCore Runtime: ARM64 必須
         ↓
Amplify Console: x86_64 のみ
         ↓
ビルド不可
```

## 解決策の案

### 案A: ECR 事前プッシュ方式（推奨）

ローカル（Mac ARM64）で Docker イメージをビルドして ECR にプッシュし、CDK で参照する。

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  ローカル Mac    │────▶│      ECR        │────▶│  Amplify Console │
│  (ARM64 ビルド)  │push │  (イメージ保存)  │参照 │  (Docker不要)    │
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

**メリット**:
- Amplify Console で Docker ビルド不要
- カスタムビルドイメージも不要（デフォルトに戻せる）
- 確実に ARM64 イメージを使用できる

**デメリット**:
- エージェントコード変更時に手動で ECR 再プッシュが必要
- Hotswap の恩恵が薄れる（イメージ更新が手動のため）

**実装方法**:
- `fromAsset()` → `fromEcrRepository()` に変更

### 案B: GitHub Actions で ECR プッシュ

GitHub Actions の ARM64 ランナーで Docker イメージをビルドし、ECR にプッシュ。

**メリット**:
- コード変更時に自動でイメージ更新
- CI/CD として完結

**デメリット**:
- GitHub Actions の追加設定が必要
- Amplify Console と GitHub Actions の連携が複雑になる

### 案C: Amplify を使わず CodePipeline + CodeBuild（ARM64）

Amplify Console を使わず、CodePipeline と ARM64 対応の CodeBuild でビルド。

**メリット**:
- ARM64 ネイティブビルドが可能
- `fromAsset()` をそのまま使用可能

**デメリット**:
- Amplify の便利な機能（プレビュー、ブランチ連携等）が使えない
- インフラ構築コストが高い

## 現状

案A（ECR 事前プッシュ方式）で進行中。

### 完了
- ECR リポジトリ作成済み: `715841358122.dkr.ecr.us-east-1.amazonaws.com/marp-agent`

### 未完了
- ローカルで Docker イメージをビルド・プッシュ
- `amplify/agent/resource.ts` を `fromEcrRepository()` に変更
- `amplify.yml` から Docker 起動設定を削除
- Amplify Console のビルドイメージをデフォルトに戻す
- コミット・プッシュして再デプロイ
