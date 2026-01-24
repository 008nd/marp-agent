# パワポ作るマン（marp-agent）実装計画

## 概要

MarpでスライドをAI生成するWebアプリケーション。非エンジニアでもブラウザから指示を出して、スライドの作成・編集・プレビュー・PDFダウンロードができる。

## 命名規則

| 用途 | 名称 |
|------|------|
| アプリ名（表示用） | パワポ作るマン |
| リポジトリ名 | marp-agent |
| リソース名（AWS） | marp-agent / marp |
| 短縮表記 | marp |

## 開発方針

```
Phase 1: ローカル開発（認証なし）
├── エージェント単体テスト（Python）
├── フロントエンド開発（React）
└── ローカルでE2E動作確認

Phase 2: Amplifyデプロイ
├── Cognito認証を有効化（本番のみ）
├── AgentCore Runtimeデプロイ
└── 本番環境テスト
```

**ポイント**: Amplify sandbox は使わず、ローカル開発 → 本番デプロイの流れ

## アーキテクチャ

```
┌─────────────────────────────────────────────────────────────────┐
│                        AWS Cloud                                 │
│  ┌─────────────────┐    ┌─────────────────────────────────────┐ │
│  │    Amplify      │    │         AgentCore Runtime           │ │
│  │  ┌───────────┐  │    │  ┌─────────────────────────────────┐│ │
│  │  │   React   │  │───▶│  │      Strands Agent             ││ │
│  │  │ Frontend  │  │SSE │  │  ┌─────────┐  ┌─────────────┐  ││ │
│  │  └───────────┘  │    │  │  │ Claude  │  │ Marp Tools  │  ││ │
│  │  ┌───────────┐  │    │  │  │ Sonnet  │  │ ・generate  │  ││ │
│  │  │  Cognito  │  │    │  │  └─────────┘  │ ・edit      │  ││ │
│  │  │   認証    │  │    │  │              │ ・preview   │  ││ │
│  │  └───────────┘  │    │  │              │ ・export    │  ││ │
│  └─────────────────┘    │  │              └─────────────────┘││ │
│                         │  └─────────────────────────────────┘│ │
│                         │                                     │ │
│                         │  ┌─────────────┐  ┌─────────────┐  │ │
│                         │  │     S3      │  │   Bedrock   │  │ │
│                         │  │ (スライド)  │  │   Claude    │  │ │
│                         │  └─────────────┘  └─────────────┘  │ │
│                         └─────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

## 技術スタック

| レイヤー | 技術 | 用途 |
|---------|------|------|
| フロントエンド | React + TypeScript (Vite) | WebUI |
| AIエージェント | Strands Agents (Python) | スライド生成ロジック |
| LLM | Bedrock Claude Sonnet 4.5 | テキスト生成 |
| スライド変換 | Marp CLI | Markdown → PDF/HTML |
| 認証 | Amplify Auth (Cognito) | ユーザー認証 |
| インフラ | AWS CDK | IaC |
| ホスティング | Amplify Hosting | フロントエンド配信 |
| ランタイム | Bedrock AgentCore | エージェント実行基盤 |
| ストレージ | S3 | スライド・PDF保存 |

## CDK Hotswap & Amplify 対応状況（2026/1/24更新）

### 背景
k.gotoさんにより、CDK hotswapがAgentCore Runtimeに対応した。
- 参考: https://go-to-k.hatenablog.com/entry/cdk-hotswap-bedrock-agentcore-runtime
- サンプル: https://github.com/go-to-k/amplify-agentcore-cdk

### 対応状況

| 項目 | 状況 |
|------|------|
| CDK hotswap | AgentCore Runtime対応済み（v1.14.0〜） |
| Amplify toolkit-lib | overridesで先行対応可能 |
| Amplify Console | **カスタムビルドイメージでDocker build可能** |

### 採用方針

```
┌─────────────────────────────────────────────────────────────┐
│  開発環境（sandbox）                                          │
│  ・AgentRuntimeArtifact.fromAsset でローカルARM64ビルド       │
│  ・deploy-time-build は使わない（macでARMビルド可能なため）     │
│  ・overridesでhotswap先行利用可能                             │
├─────────────────────────────────────────────────────────────┤
│  本番環境（Amplify Console）                                   │
│  ・deploy-time-build で CodeBuild ARM64 ビルド               │
│  ・ContainerImageBuild + fromEcrRepository() 方式            │
│  ・Amplify Console（x86_64）からARM64イメージをビルド可能      │
└─────────────────────────────────────────────────────────────┘
```

### package.json overrides設定

```json
{
  "overrides": {
    "@aws-cdk/toolkit-lib": "1.14.0",
    "@smithy/core": "^3.21.0"
  }
}
```

| パッケージ | バージョン | 理由 |
|-----------|-----------|------|
| `@aws-cdk/toolkit-lib` | `1.14.0` | AgentCore Hotswap対応版 |
| `@smithy/core` | `^3.21.0` | AWS SDKのリグレッションバグ対応 |

## 進捗状況

| ステップ | 状態 | 内容 |
|---------|------|------|
| Step 1 | ✅完了 | プロジェクト初期化（Amplify Gen2 + Vite + Tailwind） |
| Step 2 | ✅完了 | エージェント実装（Strands Agent + Marp CLI） |
| Step 3 | ✅完了 | インフラ構築（AgentCore Runtime CDK） |
| Step 4 | ✅完了 | フロントエンド実装（チャットUI、プレビュー、SSE対応） |
| Step 5 | ✅完了 | 統合・テスト（E2Eテスト全件PASS） |
| Step 6 | 🔄進行中 | 本番デプロイ（Amplify Console） |

### Step 6 詳細進捗

| 項目 | 状態 | 備考 |
|------|------|------|
| package.json overrides追加 | ✅完了 | toolkit-lib 1.14.0 |
| GitHubリポジトリ連携 | ✅完了 | mainブランチ連携済み |
| 環境変数設定 | ✅完了 | TAVILY_API_KEY設定済み |
| サービスロール作成 | ✅完了 | AmplifyServiceRole-marp-agent + AdministratorAccess-Amplify |
| deploy-time-build導入 | ✅完了 | ContainerImageBuild + fromEcrRepository方式 |
| 依存関係設定 | ✅完了 | runtime.node.addDependency(containerImageBuild) |
| 本番デプロイ実行 | 🔄進行中 | ビルド実行待ち |
| 本番動作確認 | ⬜未着手 | E2Eテスト |

### 本番デプロイで発生した問題と解決

1. **CDKAssetPublishError**: サービスロール権限不足 → ✅解決
   - デフォルトの`AmplifySSRLoggingRole`はロギング専用で権限不足
   - `AmplifyServiceRole-marp-agent`を新規作成
   - `AdministratorAccess-Amplify`ポリシーをアタッチ済み

2. **ARM64ビルド問題**: Amplify Console（x86_64）でARM64イメージをビルドできない → ✅解決
   - deploy-time-build パッケージを導入
   - ContainerImageBuild で CodeBuild ARM64 ビルドを実行
   - 詳細は docs/DEPLOY-ISSUE.md を参照

### Step 5 詳細進捗

| 項目 | 状態 | 備考 |
|------|------|------|
| Amplify初期化（main.tsx） | ✅完了 | |
| useAgentCoreフック作成 | ✅完了 | ARN URLエンコード対応済み |
| Chat.tsx API接続 | ✅完了 | VITE_USE_MOCK環境変数で切り替え |
| 環境分岐実装 | ✅完了 | AWS_BRANCHで判定、nameSuffix追加 |
| 認証UI追加 | ✅完了 | Authenticator + 日本語化 |
| 本番API接続 | ✅完了 | Cognito認証 + AgentCore SSE動作確認済み |
| ステータス表示改善 | ✅完了 | 重複防止 + Web検索/スライド生成の状態遷移 |
| PDFダウンロード | ✅完了 | 日本語対応（fonts-noto-cjk）、Base64デコード |
| E2Eテスト | ✅完了 | tests/e2e-test.md、Playwright MCP使用 |

### 解決済み: 認証問題

**エラー**: `Claim 'client_id' value mismatch with configuration.`

**原因**: IDトークンではなくアクセストークンを使用する必要があった
- IDトークン: `aud` クレームにクライアントID
- アクセストークン: `client_id` クレームにクライアントID
- AgentCoreの `usingJWT(allowedClients)` は `client_id` クレームを検証

**解決策**: `useAgentCore.ts` でアクセストークンを使用
```typescript
const accessToken = session.tokens?.accessToken?.toString();
```

### 解決済み: Bedrockモデル権限

**エラー**: `AccessDeniedException: bedrock:InvokeModelWithResponseStream on inference-profile`

**原因**: クロスリージョン推論プロファイルへの権限が不足

**解決策**: `amplify/agent/resource.ts` で権限追加
```typescript
resources: [
  'arn:aws:bedrock:*::foundation-model/*',
  'arn:aws:bedrock:*:*:inference-profile/*',  // 追加
]
```

## 機能一覧

### MVP（Phase 1）
- [x] ユーザー認証（Cognito）← 設定済み、本番のみ有効
- [x] チャットUI（指示入力）
- [x] スライド生成（Marp Markdown）
- [x] リアルタイムプレビュー（Marp Core使用）
- [x] PDFダウンロード ← 日本語対応完了（fonts-noto-cjk）

### 追加機能（Phase 2）

※ 実装の容易さ順に並べ替え済み

| # | タスク | 工数 | 備考 |
|---|--------|------|------|
| 1 | プレビュー画面の箇条書き行頭記号問題 | 小 | CSS追加のみ（2ファイル） |
| 2 | チャット画面の横幅制限 | 小 | CSS変更（1ファイル） |
| 3 | チャット応答末尾のカーソル記号を除去 | 小 | 条件確認（1ファイル） |
| 4 | チャット応答のマークダウンレンダリング | 中 | ライブラリ追加 |
| 5 | プレビュー画面から修正指示ボタン | 中 | UI追加 |
| 6 | テーマ選択 | 中 | UI + ロジック |
| 7 | スライド編集（マークダウンエディタ） | 大 | エディタライブラリ導入 |
| 8 | 画像アップロード・挿入 | 大 | S3連携 |
| 9 | スライド履歴管理 | 大 | DB連携 |

### Phase 2 タスク調査結果

#### 1. 箇条書き行頭記号問題
- **原因**: Tailwind CSS v4のプリフライトが`ul, ol { list-style: none; }`を適用
- **修正方針**: `border.css`にリストスタイルを明示的に定義
- **修正対象**: `src/themes/border.css`と`amplify/agent/runtime/border.css`の両方
- **追加CSS例**:
  ```css
  ul, ol { list-style-position: outside; }
  ul { list-style-type: disc; }
  ol { list-style-type: decimal; }
  ul ul { list-style-type: circle; }
  ```

#### 2. チャット横幅制限
- **現状**: チャットコンテナに横幅制限がなく全幅使用
- **修正方針**: App.tsxの`<main>`内に`max-w-4xl mx-auto`ラッパーを追加
- **実装例**:
  ```tsx
  <main className="flex-1 overflow-hidden bg-gray-50">
    <div className="h-full flex justify-center">
      <div className="w-full max-w-4xl flex flex-col">
        <Chat ... />
      </div>
    </div>
  </main>
  ```

#### 3. カーソル記号問題
- **原因**: `Chat.tsx:230`で意図的に表示している `▌` 記号
- **コード**: `{message.isStreaming && <span className="animate-pulse">▌</span>}`
- **修正方針**: ストリーミング完了時の`isStreaming`フラグ更新タイミングを見直し

## ドキュメント構成

開発開始時に `/docs` 配下へ移動：
```
docs/
├── PLAN.md       # 実装計画
├── SPEC.md       # 仕様書
└── KNOWLEDGE.md  # ナレッジベース（随時更新）
```

---

## ディレクトリ構成

```
marp-agent/
├── docs/                        # ドキュメント
│   ├── PLAN.md
│   ├── SPEC.md
│   └── KNOWLEDGE.md
├── amplify/
│   ├── auth/
│   │   └── resource.ts          # Cognito認証設定 ✅
│   ├── agent/
│   │   ├── resource.ts          # AgentCore CDK定義 ✅
│   │   └── runtime/
│   │       ├── Dockerfile       # エージェントコンテナ ✅
│   │       ├── requirements.txt # Python依存関係 ✅
│   │       ├── pyproject.toml   # uv管理用 ✅
│   │       ├── border.css       # カスタムテーマ（PDF生成用） ✅
│   │       └── agent.py         # Strands Agent実装 ✅
│   └── backend.ts               # バックエンド統合 ✅
├── tests/
│   ├── test_agent.py            # エージェント単体テスト ✅
│   ├── e2e-test.md              # E2Eテストチェックリスト ✅
│   └── screenshots/             # テスト用スクリーンショット（.gitignore）
├── src/
│   ├── App.tsx                  # メインアプリ + Authenticator ✅
│   ├── components/
│   │   ├── Chat.tsx             # チャットUI ✅
│   │   └── SlidePreview.tsx     # スライドプレビュー ✅
│   ├── hooks/
│   │   └── useAgentCore.ts      # AgentCore API呼び出しフック ✅
│   ├── themes/
│   │   └── border.css           # カスタムテーマ（プレビュー用） ✅
│   ├── index.css                # Tailwind + カスタムカラー ✅
│   └── main.tsx                 # Amplify初期化 + I18n ✅
├── index.html                   # HTMLテンプレート ✅
├── vite.config.ts               # Vite + Tailwind設定 ✅
├── package.json
└── tsconfig.json
```

## Strands Agent 設計

### システムプロンプト

```
あなたはスライド作成のプロフェッショナルです。
ユーザーの指示に基づいて、Marp形式のマークダウンでスライドを作成します。

ルール：
- スライド区切りは `---` を使用
- 最初のスライドにはタイトルと副題を入れる
- 箇条書きは簡潔に
- 絵文字は使用しない（ビジネスライク）
- marp: true をフロントマターに含める
```

### エージェント機能

| 機能 | 説明 | 状態 |
|------|------|------|
| スライド生成・編集 | LLMによるMarp Markdown生成 | ✅ 実装済み |
| PDF出力 | Marp CLIでPDF変換 | ✅ 実装済み（エージェント側） |
| Web検索 | Tavily APIで最新情報取得 | ✅ 実装済み |
| output_slide | マークダウン出力用ツール | ✅ 実装済み |

**備考**:
- プレビューはフロントエンド側で@marp-team/marp-coreを使用して描画
- PDF生成はエージェント側の`action: "export_pdf"`で実行可能

## 実装ステップ

### Step 1: プロジェクト初期化 ✅
1. ✅ Amplify Gen2プロジェクト作成（npm create amplify）
2. ✅ 認証設定（Cognito）← 本番デプロイ時に有効化
3. ✅ 基本的なReact UI（Vite + Tailwind CSS v4）

### Step 2: エージェント実装 ✅
1. ✅ Strands Agent 作成（agent.py）
2. ✅ Marp CLI をDockerfileに追加
3. ✅ 機能実装（generate, edit, export_pdf）
4. ✅ 単体テスト実行・成功

### Step 3: インフラ構築 ✅
1. ✅ AgentCore Runtime CDK定義（amplify/agent/resource.ts）
2. ✅ Cognito認証統合（JWT認証）
3. ✅ Bedrockモデル権限設定（inference-profile対応）

### Step 4: フロントエンド実装 ✅
1. ✅ チャットUI（タブ切り替え）
2. ✅ SSEストリーミング対応
3. ✅ スライドプレビューコンポーネント
4. ✅ PDFダウンロード機能

### Step 5: 統合・テスト ✅
1. ✅ ローカルE2Eテスト
2. 🔄 本番デプロイ（Amplify Console）← Step 6へ移行

## 決定済み事項

| 項目 | 決定 |
|------|------|
| 認証 | ローカル開発時はなし、本番のみCognito認証 |
| 保存 | MVPではセッション限り（フロントエンドstate） |
| テーマ | borderテーマ（コミュニティテーマ） |
| 共同編集 | 不要 |
| UIレイアウト | タブ切り替え（チャット / プレビュー） |
| モデル | Claude Sonnet 4.5 |
| リージョン | us-east-1 |

## 参考リンク

- [Marp公式ドキュメント](https://marp.app/)
- [Strands Agents](https://github.com/strands-agents/strands-agents)
- [Amplify Gen2](https://docs.amplify.aws/gen2/)
- [Bedrock AgentCore](https://docs.aws.amazon.com/bedrock/latest/userguide/agents-agentcore.html)
- [参考実装: Amplify × AgentCore](https://qiita.com/minorun365/items/0b4a980f2f4bb073a9e0)
- [CDK Hotswap × AgentCore Runtime](https://go-to-k.hatenablog.com/entry/cdk-hotswap-bedrock-agentcore-runtime)
