# 本番デプロイ問題整理

## 問題

Amplify Console での本番デプロイが失敗している。

## 根本原因

| 環境 | アーキテクチャ |
|------|---------------|
| AgentCore Runtime | ARM64 のみ対応 |
| Amplify Console ビルド環境 | x86_64 のみ対応 |

→ **Amplify Console では ARM64 Docker イメージをビルドできない**

## 解決策: ECR 事前プッシュ方式

ローカル（Mac ARM64）で Docker イメージをビルドして ECR にプッシュし、CDK で参照する。

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  ローカル Mac    │────▶│      ECR        │────▶│  Amplify Console │
│  (ARM64 ビルド)  │push │  (イメージ保存)  │参照 │  (Docker不要)    │
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

**ポイント**: ECR からイメージを参照するだけなので、Amplify Console 側で Docker は不要。カスタムビルドイメージもデフォルトに戻せる。

## 手順

1. ✅ ECR リポジトリ作成済み
   ```
   715841358122.dkr.ecr.us-east-1.amazonaws.com/marp-agent
   ```

2. ⬜ ローカルで Docker イメージをビルド・プッシュ
   ```bash
   cd amplify/agent/runtime
   docker build -t marp-agent .
   docker tag marp-agent:latest 715841358122.dkr.ecr.us-east-1.amazonaws.com/marp-agent:latest
   docker push 715841358122.dkr.ecr.us-east-1.amazonaws.com/marp-agent:latest
   ```

3. ⬜ `amplify/agent/resource.ts` を修正
   - `fromAsset()` → `fromEcrRepository()` に変更

4. ⬜ `amplify.yml` から Docker 起動設定を削除

5. ⬜ Amplify Console のビルドイメージをデフォルトに戻す

6. ⬜ コミット・プッシュして再デプロイ

## 運用上の注意

- エージェントコード（agent.py 等）を変更した場合、手動で ECR に再プッシュが必要
- 将来的には GitHub Actions で自動化を検討
