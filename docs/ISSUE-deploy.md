# 本番デプロイ問題整理

## 問題

Amplify Console での本番デプロイが失敗している。

## 根本原因

| 環境 | アーキテクチャ |
|------|---------------|
| AgentCore Runtime | ARM64 のみ対応 |
| Amplify Console ビルド環境 | x86_64 のみ対応 |

→ **Amplify Console では ARM64 Docker イメージを直接ビルドできない**

## 解決策: 環境分岐（deploy-time-build）

ごとうさんのアドバイスに基づき、環境によってビルド方式を分岐させる。

```
┌─────────────────────────────────────────────────────────────┐
│  sandbox（ローカル開発）                                      │
│  ・fromAsset() でローカル ARM64 ビルド                       │
│  ・Mac の Docker でネイティブビルド                          │
├─────────────────────────────────────────────────────────────┤
│  本番（Amplify Console）                                     │
│  ・deploy-time-build で CodeBuild ARM64 ビルド              │
│  ・ContainerImageBuild + fromEcrRepository()                │
└─────────────────────────────────────────────────────────────┘
```

### 使用ライブラリ

- [deploy-time-build](https://github.com/tmokmss/deploy-time-build) by 友岡さん
  - CodeBuild でデプロイ時にコンテナイメージをビルド
  - `platform: Platform.LINUX_ARM64` で ARM64 対応

### 実装

```typescript
// amplify/agent/resource.ts
const isSandbox = !process.env.AWS_BRANCH;

if (isSandbox) {
  // sandbox: ローカルでARM64ビルド
  agentRuntimeArtifact = agentcore.AgentRuntimeArtifact.fromAsset(
    path.join(__dirname, 'runtime')
  );
} else {
  // 本番: CodeBuildでARM64ビルド
  const containerImageBuild = new ContainerImageBuild(stack, 'MarpAgentImageBuild', {
    directory: path.join(__dirname, 'runtime'),
    platform: Platform.LINUX_ARM64,
    tag: 'latest',
  });
  agentRuntimeArtifact = agentcore.AgentRuntimeArtifact.fromEcrRepository(
    containerImageBuild.repository,
    'latest'
  );
}

// 依存関係設定（イメージビルド完了後にRuntime作成）
if (containerImageBuild) {
  runtime.node.addDependency(containerImageBuild);
}
```

### 依存関係設定の重要性

`runtime.node.addDependency(containerImageBuild)` により、CloudFormation が以下の順序でリソースを作成する：

1. ContainerImageBuild（CodeBuild で ARM64 イメージをビルド）
2. ECR にイメージがプッシュされる
3. AgentCore Runtime が ECR イメージを参照して作成される

この設定がないと、Runtime 作成時にまだイメージが存在せずエラーになる。

## 注意事項

- deploy-time-build を使う場合、hotswap デプロイは動作しない（CloudFormation トークン解決の問題）
- 本番デプロイは通常のCloudFormationデプロイとなる

## 参考

- [CDK Hotswap × AgentCore Runtime](https://go-to-k.hatenablog.com/entry/cdk-hotswap-bedrock-agentcore-runtime) by ごとうさん
- [deploy-time-build](https://github.com/tmokmss/deploy-time-build) by 友岡さん
