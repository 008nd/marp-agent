import * as path from 'path';
import * as url from 'url';
import * as cdk from 'aws-cdk-lib';
import * as iam from 'aws-cdk-lib/aws-iam';
import * as agentcore from '@aws-cdk/aws-bedrock-agentcore-alpha';
import type { IUserPool, IUserPoolClient } from 'aws-cdk-lib/aws-cognito';

// ESモジュールで__dirnameを取得
const __filename = url.fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

interface MarpAgentProps {
  stack: cdk.Stack;
  userPool?: IUserPool;
  userPoolClient?: IUserPoolClient;
  nameSuffix?: string;
}

export function createMarpAgent({ stack, userPool, userPoolClient, nameSuffix }: MarpAgentProps) {
  // ローカルDockerイメージからビルド（ARM64）
  const agentRuntimeArtifact = agentcore.AgentRuntimeArtifact.fromAsset(
    path.join(__dirname, 'runtime')
  );

  // 認証設定（JWT認証）
  // usingCognito()はclient_id/audienceの両方を検証するため、
  // より細かく制御できるusingJWT()を使用
  const discoveryUrl = userPool
    ? `https://cognito-idp.${stack.region}.amazonaws.com/${userPool.userPoolId}/.well-known/openid-configuration`
    : undefined;

  const authConfig = discoveryUrl && userPoolClient
    ? agentcore.RuntimeAuthorizerConfiguration.usingJWT(
        discoveryUrl,
        [userPoolClient.userPoolClientId], // allowedClients
        // allowedAudience は省略（Resource Server未使用のため）
      )
    : undefined;

  // 環境ごとのランタイム名（例: marp_agent_dev, marp_agent_main）
  const runtimeName = nameSuffix ? `marp_agent_${nameSuffix}` : 'marp_agent';

  // AgentCore Runtime作成
  const runtime = new agentcore.Runtime(stack, 'MarpAgentRuntime', {
    runtimeName,
    agentRuntimeArtifact,
    authorizerConfiguration: authConfig,
    environmentVariables: {
      TAVILY_API_KEY: process.env.TAVILY_API_KEY || '',
    },
  });

  // Bedrockモデル呼び出し権限を付与（全モデル + 推論プロファイル）
  runtime.addToRolePolicy(new iam.PolicyStatement({
    actions: [
      'bedrock:InvokeModel',
      'bedrock:InvokeModelWithResponseStream',
    ],
    resources: [
      'arn:aws:bedrock:*::foundation-model/*',
      'arn:aws:bedrock:*:*:inference-profile/*',
    ],
  }));

  // エンドポイント作成
  const endpoint = runtime.addEndpoint('marp_agent_endpoint');

  // 出力
  new cdk.CfnOutput(stack, 'MarpAgentRuntimeArn', {
    value: runtime.agentRuntimeArn,
    description: 'Marp Agent Runtime ARN',
  });

  new cdk.CfnOutput(stack, 'MarpAgentEndpointArn', {
    value: endpoint.agentRuntimeEndpointArn,
    description: 'Marp Agent Endpoint ARN',
  });

  return { runtime, endpoint };
}
