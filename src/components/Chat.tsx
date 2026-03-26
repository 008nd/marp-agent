import { useState, useRef, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import { invokeAgent, invokeAgentMock } from '../hooks/useAgentCore';
import type { ModelType } from '../hooks/useAgentCore';

interface Message {
  role: 'user' | 'assistant';
  content: string;
  isStreaming?: boolean;
  isStatus?: boolean;  // ステータス表示用メッセージ
  statusText?: string; // ステータステキスト
  tipIndex?: number;   // 豆知識ローテーション用
}

// スライド生成中に表示する豆知識
const TIPS = [
  'このアプリはOpenAI APIでスライドを生成します。',
  '元のアプリはBedrockからClaudeを呼び出すものでしたが、OpenAI APIに作り変えました。',
  'このアプリはサーバーレス構成なので維持費が安いです。',
  '元となったアプリの開発者はみのるん（Xアカウント @minorun365） です。',
];

interface ChatProps {
  onMarkdownGenerated: (markdown: string) => void;
  currentMarkdown: string;
  inputRef?: React.RefObject<HTMLTextAreaElement | null>;
  editPromptTrigger?: number;  // 値が変わるたびに修正用メッセージを表示
  sharePromptTrigger?: number;  // 値が変わるたびにシェア用メッセージを自動送信
  sessionId?: string;  // 会話履歴を保持するためのセッションID
  theme?: string;
}

// モック使用フラグ（VITE_USE_MOCK=true で強制的にモック使用）
const useMock = import.meta.env.VITE_USE_MOCK === 'true';

// UIメッセージ定数
const MESSAGES = {
  // 初期・プロンプト
  INITIAL: 'どんな資料を作りたいですか？ URLの要約もできます！',
  EDIT_PROMPT: 'どのように修正しますか？ 内容や枚数の調整、はみ出しの抑制もできます！',
  EMPTY_STATE_TITLE: 'スライドを作成しましょう',
  EMPTY_STATE_EXAMPLE: '例: 「AWS入門の5枚スライドを作って」',
  ERROR: 'エラーが発生しました。もう一度お試しください。',
  ERROR_MODEL_NOT_AVAILABLE: '指定したOpenAIモデルが利用できません。モデル名と権限を確認してください。',

  // ステータス - スライド生成
  SLIDE_GENERATING_PREFIX: 'スライドを作成中...',
  SLIDE_GENERATING: 'スライドを作成中...',
  SLIDE_COMPLETED: 'スライドを作成しました',

  // ステータス - Web検索
  WEB_SEARCH_PREFIX: 'Web検索中...',
  WEB_SEARCH_DEFAULT: 'Web検索中...',
  WEB_SEARCH_COMPLETED: 'Web検索完了',

  // ステータス - ツイート
  TWEET_GENERATING: 'ツイート案を作成中...',
  TWEET_COMPLETED: 'ツイート案を作成しました',
} as const;

// 検索クエリ付きのステータスを生成
const getWebSearchStatus = (query?: string) =>
  query ? `${MESSAGES.WEB_SEARCH_PREFIX} "${query}"` : MESSAGES.WEB_SEARCH_DEFAULT;

// シェアメッセージを生成
const getShareMessage = (url: string) =>
  `ダウンロードありがとうございます！今回の体験をXでシェアしませんか？ 👉 [ツイート](${url})`;

export function Chat({ onMarkdownGenerated, currentMarkdown, inputRef, editPromptTrigger, sharePromptTrigger, sessionId, theme = 'gradient' }: ChatProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [status, setStatus] = useState('');
  const [modelType] = useState<ModelType>('standard');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const initializedRef = useRef(false);
  const tipTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const tipIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  // コンポーネントアンマウント時に豆知識タイマーをクリア
  useEffect(() => {
    return () => {
      if (tipTimeoutRef.current) {
        clearTimeout(tipTimeoutRef.current);
      }
      if (tipIntervalRef.current) {
        clearInterval(tipIntervalRef.current);
      }
    };
  }, []);

  // 初期メッセージをストリーミング表示
  useEffect(() => {
    if (initializedRef.current) return;
    initializedRef.current = true;

    const streamInitialMessage = async () => {
      setMessages([{ role: 'assistant', content: '', isStreaming: true }]);

      for (const char of MESSAGES.INITIAL) {
        await new Promise(resolve => setTimeout(resolve, 30));
        setMessages(prev =>
          prev.map((msg, idx) =>
            idx === 0 ? { ...msg, content: msg.content + char } : msg
          )
        );
      }

      setMessages(prev =>
        prev.map((msg, idx) =>
          idx === 0 ? { ...msg, isStreaming: false } : msg
        )
      );
    };

    streamInitialMessage();
  }, []);

  // 修正依頼ボタンが押されたときのストリーミングメッセージ
  useEffect(() => {
    if (!editPromptTrigger || editPromptTrigger === 0) return;

    const streamEditPrompt = async () => {
      // 既存の「どのように修正しますか？」メッセージを削除してから追加
      setMessages(prev => {
        const filtered = prev.filter(
          msg => !(msg.role === 'assistant' && msg.content === MESSAGES.EDIT_PROMPT)
        );
        return [...filtered, { role: 'assistant', content: '', isStreaming: true }];
      });

      for (const char of MESSAGES.EDIT_PROMPT) {
        await new Promise(resolve => setTimeout(resolve, 30));
        setMessages(prev =>
          prev.map((msg, idx) =>
            idx === prev.length - 1 && msg.role === 'assistant' && msg.isStreaming
              ? { ...msg, content: msg.content + char }
              : msg
          )
        );
      }

      setMessages(prev =>
        prev.map((msg, idx) =>
          idx === prev.length - 1 && msg.isStreaming
            ? { ...msg, isStreaming: false }
            : msg
        )
      );
    };

    streamEditPrompt();
  }, [editPromptTrigger]);

  // シェアボタンが押されたときにエージェントにシェアリクエストを自動送信
  useEffect(() => {
    if (!sharePromptTrigger || sharePromptTrigger === 0 || isLoading) return;

    const sendShareRequest = async () => {
      setIsLoading(true);

      // アシスタントメッセージを追加（ストリーミング用）
      setMessages(prev => [...prev, { role: 'assistant', content: '', isStreaming: true }]);

      try {
        const invoke = useMock ? invokeAgentMock : invokeAgent;

        await invoke('今回の体験をXでシェアするURLを提案してください（無言でツール使用開始すること）', currentMarkdown, theme, {
          onText: (text) => {
            setMessages(prev =>
              prev.map((msg, idx) =>
                idx === prev.length - 1 && msg.role === 'assistant' && !msg.isStatus
                  ? { ...msg, content: msg.content + text }
                  : msg
              )
            );
          },
          onStatus: () => {},
          onToolUse: (toolName) => {
            // ストリーミングカーソルを消す
            setMessages(prev =>
              prev.map(msg =>
                msg.isStreaming ? { ...msg, isStreaming: false } : msg
              )
            );

            if (toolName === 'generate_tweet_url') {
              setMessages(prev => {
                const hasExisting = prev.some(
                  msg => msg.isStatus && msg.statusText === MESSAGES.TWEET_GENERATING
                );
                if (hasExisting) return prev;
                return [
                  ...prev,
                  { role: 'assistant', content: '', isStatus: true, statusText: MESSAGES.TWEET_GENERATING }
                ];
              });
            }
            // シェアリクエスト時はスライド生成ステータスは無視
          },
          onMarkdown: () => {},
          onTweetUrl: (url) => {
            // ツイートURLステータスを完了に更新し、リンクメッセージを追加
            setMessages(prev => {
              const updated = prev.map(msg =>
                msg.isStatus && msg.statusText === MESSAGES.TWEET_GENERATING
                  ? { ...msg, statusText: MESSAGES.TWEET_COMPLETED }
                  : msg
              );
              return [
                ...updated,
                { role: 'assistant', content: getShareMessage(url) }
              ];
            });
          },
          onError: (error) => {
            console.error('Share error:', error);
          },
          onComplete: () => {
            setMessages(prev =>
              prev.map(msg => {
                if (msg.isStreaming) {
                  return { ...msg, isStreaming: false };
                }
                // ツイートステータスを確実に完了に更新
                if (msg.isStatus && msg.statusText === MESSAGES.TWEET_GENERATING) {
                  return { ...msg, statusText: MESSAGES.TWEET_COMPLETED };
                }
                return msg;
              })
            );
          },
        }, sessionId, modelType);
      } catch (error) {
        console.error('Error:', error);
      } finally {
        setIsLoading(false);
      }
    };

    sendShareRequest();
  }, [sharePromptTrigger, currentMarkdown, isLoading, modelType, sessionId, theme]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;

    const userMessage = input.trim();
    setInput('');
    setMessages(prev => [...prev, { role: 'user', content: userMessage }]);
    setIsLoading(true);
    setStatus('考え中...');

    // アシスタントメッセージを追加（ストリーミング用）
    setMessages(prev => [...prev, { role: 'assistant', content: '', isStreaming: true }]);

    try {
      // デフォルトは本番API、VITE_USE_MOCK=trueでモック使用
      const invoke = useMock ? invokeAgentMock : invokeAgent;

      await invoke(userMessage, currentMarkdown, theme, {
        onText: (text) => {
          setStatus(''); // テキストが来たらステータスを消す
          // テキストをストリーミング表示
          setMessages(prev => {
            // テキストが来たら進行中のWeb検索ステータスを完了にする
            const msgs = prev.map(msg =>
              msg.isStatus && msg.statusText?.startsWith(MESSAGES.WEB_SEARCH_PREFIX)
                ? { ...msg, statusText: MESSAGES.WEB_SEARCH_COMPLETED }
                : msg
            );
            // 最後のステータスメッセージと最後の非ステータスアシスタントメッセージのインデックスを探す
            let lastStatusIdx = -1;
            let lastTextAssistantIdx = -1;
            for (let i = msgs.length - 1; i >= 0; i--) {
              if (msgs[i].isStatus && lastStatusIdx === -1) {
                lastStatusIdx = i;
              }
              if (msgs[i].role === 'assistant' && !msgs[i].isStatus && lastTextAssistantIdx === -1) {
                lastTextAssistantIdx = i;
              }
            }
            // ステータスがあり、その後にテキストメッセージがない場合は新しいメッセージを追加
            if (lastStatusIdx !== -1 && (lastTextAssistantIdx === -1 || lastTextAssistantIdx < lastStatusIdx)) {
              return [...msgs, { role: 'assistant', content: text, isStreaming: true }];
            }
            // そうでなければ、最後の非ステータスアシスタントメッセージにテキストを追加
            if (lastTextAssistantIdx !== -1) {
              return msgs.map((msg, idx) =>
                idx === lastTextAssistantIdx ? { ...msg, content: msg.content + text } : msg
              );
            }
            // どちらもなければ新しいメッセージを追加
            return [...msgs, { role: 'assistant', content: text, isStreaming: true }];
          });
        },
        onStatus: (newStatus) => {
          setStatus(newStatus);
        },
        onToolUse: (toolName, query) => {
          // ツール使用開始時にストリーミングカーソルを消す
          setMessages(prev =>
            prev.map(msg =>
              msg.isStreaming ? { ...msg, isStreaming: false } : msg
            )
          );

          // ツール使用中のステータスを表示（既存のステータスがなければ追加）
          if (toolName === 'output_slide') {
            // 既存のタイマーをクリア
            if (tipTimeoutRef.current) {
              clearTimeout(tipTimeoutRef.current);
              tipTimeoutRef.current = null;
            }
            if (tipIntervalRef.current) {
              clearInterval(tipIntervalRef.current);
              tipIntervalRef.current = null;
            }

            setMessages(prev => {
              // Web検索があれば完了に更新し、output_slideのステータスを追加
              const hasExisting = prev.some(
                msg => msg.isStatus && msg.statusText?.startsWith(MESSAGES.SLIDE_GENERATING_PREFIX)
              );
              if (hasExisting) return prev;

              // Web検索中を完了に更新
              const updated = prev.map(msg =>
                msg.isStatus && msg.statusText?.startsWith(MESSAGES.WEB_SEARCH_PREFIX)
                  ? { ...msg, statusText: MESSAGES.WEB_SEARCH_COMPLETED }
                  : msg
              );
              return [
                ...updated,
                { role: 'assistant', content: '', isStatus: true, statusText: MESSAGES.SLIDE_GENERATING, tipIndex: undefined }
              ];
            });

            // ランダムにTipsを選択する関数（前回と異なるものを選択）
            const getRandomTipIndex = (currentIndex?: number): number => {
              let newIndex: number;
              do {
                newIndex = Math.floor(Math.random() * TIPS.length);
              } while (TIPS.length > 1 && newIndex === currentIndex);
              return newIndex;
            };

            // 3秒後に最初のTipsを表示
            tipTimeoutRef.current = setTimeout(() => {
              setMessages(prev =>
                prev.map(msg =>
                  msg.isStatus && msg.statusText?.startsWith(MESSAGES.SLIDE_GENERATING_PREFIX)
                    ? { ...msg, tipIndex: getRandomTipIndex() }
                    : msg
                )
              );

              // その後5秒ごとにランダムにローテーション
              tipIntervalRef.current = setInterval(() => {
                setMessages(prev =>
                  prev.map(msg =>
                    msg.isStatus && msg.statusText?.startsWith(MESSAGES.SLIDE_GENERATING_PREFIX)
                      ? { ...msg, tipIndex: getRandomTipIndex(msg.tipIndex) }
                      : msg
                  )
                );
              }, 5000);
            }, 3000);
          } else if (toolName === 'web_search') {
            const searchStatus = getWebSearchStatus(query);
            setMessages(prev => {
              // 同じクエリの検索中ステータスが既にあればスキップ（同一呼び出しの重複防止）
              const hasInProgress = prev.some(
                msg => msg.isStatus && msg.statusText === searchStatus
              );
              if (hasInProgress) return prev;

              // 既存のWeb検索中ステータス（完了以外）を削除して、新しいステータスを追加
              // これにより「Web検索中」の吹き出しは常に1つだけになる
              const filtered = prev.filter(
                msg => !(msg.isStatus && msg.statusText?.startsWith(MESSAGES.WEB_SEARCH_PREFIX) && msg.statusText !== MESSAGES.WEB_SEARCH_COMPLETED)
              );
              return [
                ...filtered,
                { role: 'assistant', content: '', isStatus: true, statusText: searchStatus }
              ];
            });
          }
        },
        onMarkdown: (markdown) => {
          onMarkdownGenerated(markdown);
          // 豆知識ローテーションタイマーをクリア
          if (tipTimeoutRef.current) {
            clearTimeout(tipTimeoutRef.current);
            tipTimeoutRef.current = null;
          }
          if (tipIntervalRef.current) {
            clearInterval(tipIntervalRef.current);
            tipIntervalRef.current = null;
          }
          // output_slideのステータスを完了状態に更新
          setMessages(prev =>
            prev.map(msg =>
              msg.isStatus && msg.statusText?.startsWith(MESSAGES.SLIDE_GENERATING_PREFIX)
                ? { ...msg, statusText: MESSAGES.SLIDE_COMPLETED, tipIndex: undefined }
                : msg
            )
          );
        },
        onError: (error) => {
          console.error('Agent error:', error);
          // モデルが未リリースの場合は専用メッセージを表示
          const errorMessage = error instanceof Error ? error.message : String(error);
          const isModelNotAvailable =
            /model/i.test(errorMessage) &&
            (errorMessage.includes('not found') ||
              errorMessage.includes('model_not_found') ||
              errorMessage.includes('does not exist'));
          const displayMessage = isModelNotAvailable ? MESSAGES.ERROR_MODEL_NOT_AVAILABLE : MESSAGES.ERROR;

          // 疑似ストリーミングでエラーメッセージを表示
          // finallyブロックとの競合を避けるため、isStreamingのチェックを緩和
          const streamErrorMessage = async () => {
            // ステータスメッセージを削除し、空のアシスタントメッセージを追加
            setMessages(prev => {
              const filtered = prev.filter(msg => !msg.isStatus);
              return [...filtered, { role: 'assistant' as const, content: '', isStreaming: true }];
            });

            // 1文字ずつ表示（isStreaming: trueを維持してカーソル表示を継続）
            for (const char of displayMessage) {
              await new Promise(resolve => setTimeout(resolve, 30));
              setMessages(prev =>
                prev.map((msg, idx) =>
                  idx === prev.length - 1 && msg.role === 'assistant'
                    ? { ...msg, content: msg.content + char, isStreaming: true }
                    : msg
                )
              );
            }

            // ストリーミング完了
            setMessages(prev =>
              prev.map((msg, idx) =>
                idx === prev.length - 1 && msg.role === 'assistant'
                  ? { ...msg, isStreaming: false }
                  : msg
              )
            );
            setIsLoading(false);
            setStatus('');
          };

          streamErrorMessage();
        },
        onComplete: () => {
          // Web検索のステータスも完了に更新
          setMessages(prev =>
            prev.map(msg =>
              msg.isStatus && msg.statusText?.startsWith(MESSAGES.WEB_SEARCH_PREFIX)
                ? { ...msg, statusText: MESSAGES.WEB_SEARCH_COMPLETED }
                : msg
            )
          );
        },
      }, sessionId, modelType);

      // ストリーミング完了
      setMessages(prev =>
        prev.map(msg =>
          msg.role === 'assistant' && msg.isStreaming
            ? { ...msg, isStreaming: false }
            : msg
        )
      );
    } catch (error) {
      console.error('Error:', error);
      // モデルが未リリースの場合は専用メッセージを表示
      const errorMessage = error instanceof Error ? error.message : String(error);
      const isModelNotAvailable =
        /model/i.test(errorMessage) &&
        (errorMessage.includes('not found') ||
          errorMessage.includes('model_not_found') ||
          errorMessage.includes('does not exist'));
      const displayMessage = isModelNotAvailable ? MESSAGES.ERROR_MODEL_NOT_AVAILABLE : MESSAGES.ERROR;

      // ステータスメッセージを削除し、エラーメッセージを表示
      setMessages(prev => {
        // ステータスメッセージを除外
        const filtered = prev.filter(msg => !msg.isStatus);
        // 最後のアシスタントメッセージを探す
        const lastAssistantIdx = filtered.findIndex((msg, idx) =>
          idx === filtered.length - 1 && msg.role === 'assistant'
        );
        if (lastAssistantIdx !== -1) {
          // 既存のアシスタントメッセージを更新
          return filtered.map((msg, idx) =>
            idx === lastAssistantIdx
              ? { ...msg, content: displayMessage, isStreaming: false }
              : msg
          );
        } else {
          // アシスタントメッセージがなければ新規追加
          return [...filtered, { role: 'assistant' as const, content: displayMessage, isStreaming: false }];
        }
      });
    } finally {
      setIsLoading(false);
      setStatus('');
      // 豆知識タイマーをクリア
      if (tipTimeoutRef.current) {
        clearTimeout(tipTimeoutRef.current);
        tipTimeoutRef.current = null;
      }
      if (tipIntervalRef.current) {
        clearInterval(tipIntervalRef.current);
        tipIntervalRef.current = null;
      }
      // 確実に全てのストリーミング状態を解除
      setMessages(prev =>
        prev.map(msg =>
          msg.isStreaming ? { ...msg, isStreaming: false } : msg
        )
      );
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* メッセージ一覧 */}
      <div className="flex-1 overflow-y-auto px-6 py-4">
        <div className="max-w-3xl mx-auto space-y-4">
        {/* <div className="bg-blue-50 border border-blue-200 rounded-lg px-4 py-3 text-blue-700 text-sm">
          ⚠️ 高速モデルは出力が簡略化される場合があります。
        </div> */}
        {messages.length === 0 && (
          <div className="text-center text-gray-400 mt-8">
            <p className="text-lg">{MESSAGES.EMPTY_STATE_TITLE}</p>
            <p className="text-sm mt-2">{MESSAGES.EMPTY_STATE_EXAMPLE}</p>
          </div>
        )}
        {messages.map((message, index) => {
          const isLastAssistant = message.role === 'assistant' && index === messages.length - 1;
          const showStatus = isLastAssistant && !message.content && !message.isStatus && status;

          // 空のアシスタントメッセージはスキップ（ステータス表示中を除く）
          if (message.role === 'assistant' && !message.isStatus && !message.content.trim() && !showStatus) {
            return null;
          }

          // ステータスメッセージの場合
          if (message.isStatus) {
            const isSlideGenerating = message.statusText?.startsWith(MESSAGES.SLIDE_GENERATING_PREFIX);
            const isWebSearching = message.statusText?.startsWith(MESSAGES.WEB_SEARCH_PREFIX) && message.statusText !== MESSAGES.WEB_SEARCH_COMPLETED;
            const currentTip = isSlideGenerating && message.tipIndex !== undefined ? TIPS[message.tipIndex] : null;

            return (
              <div key={isWebSearching ? `web-search-${message.statusText}` : index} className="flex justify-start">
                <div className={`bg-blue-50 text-blue-700 rounded-lg px-4 py-2 border border-blue-200 ${isWebSearching ? 'animate-fade-in' : ''}`}>
                  <span className="text-sm flex items-center gap-2">
                    {message.statusText === MESSAGES.SLIDE_COMPLETED || message.statusText === MESSAGES.WEB_SEARCH_COMPLETED || message.statusText === MESSAGES.TWEET_COMPLETED ? (
                      <span className="text-green-600">&#10003;</span>
                    ) : (
                      <span className="animate-spin">&#9696;</span>
                    )}
                    {message.statusText}
                  </span>
                  {currentTip && (
                    <p
                      key={message.tipIndex}
                      className="text-xs text-gray-400 mt-2 animate-fade-in"
                    >
                      Tips: {currentTip}
                    </p>
                  )}
                </div>
              </div>
            );
          }

          return (
            <div
              key={index}
              className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div
                className={`max-w-[80%] rounded-lg px-4 py-2 ${
                  message.role === 'user'
                    ? 'bg-kag-gradient text-white'
                    : 'bg-gray-100 text-gray-800'
                }`}
              >
                {showStatus ? (
                  <span className="text-sm shimmer-text font-medium">{status}</span>
                ) : message.role === 'assistant' ? (
                  <div className="text-sm prose prose-sm max-w-none prose-p:my-1 prose-ul:my-1 prose-ol:my-1 prose-li:my-0">
                    <ReactMarkdown
                      components={{
                        a: ({ href, children }) => (
                          <a href={href} target="_blank" rel="noopener noreferrer">
                            {children}
                          </a>
                        ),
                      }}
                    >
                      {message.content + (message.isStreaming ? ' ▌' : '')}
                    </ReactMarkdown>
                  </div>
                ) : (
                  <pre className="whitespace-pre-wrap font-sans text-sm">
                    {message.content}
                  </pre>
                )}
              </div>
            </div>
          );
        })}
          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* 入力フォーム */}
      <form onSubmit={handleSubmit} className="border-t px-6 py-4">
        <div className="max-w-3xl mx-auto flex gap-2">
          {/* 入力欄 */}
          <div className="flex-1 flex items-center border border-gray-200 rounded-lg bg-gray-50 focus-within:ring-2 focus-within:ring-[#5ba4d9] focus-within:border-transparent">
            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="例：Marpの入門資料つくって"
              rows={2}
              className="flex-1 bg-transparent px-3 py-2 focus:outline-none placeholder:text-gray-400 resize-none"
              disabled={isLoading}
            />
          </div>
          <button
            type="submit"
            disabled={isLoading || !input.trim()}
            className="btn-kag text-white px-4 sm:px-6 py-2 rounded-lg whitespace-nowrap"
          >
            送信
          </button>
        </div>
      </form>
    </div>
  );
}
