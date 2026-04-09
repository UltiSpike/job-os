// 本地关键词分类器 — 0ms 提取技能 topic，无需 LLM
//
// 字典覆盖：K8s 生态 / Golang / 数据库 / 中间件 / 系统设计 / 云原生 / GPU
// 命中规则：text 中（不区分大小写）出现任意 pattern 即添加该 topic
//
// 设计原则：
// - canonical topic 用英文小写，跟后端 LLM classify 输出保持一致
// - 长 pattern 优先（先匹配 "kubernetes" 再匹配 "k8s"，避免 "8s" 误判）
// - 中文 pattern 直接 includes 检测；英文 pattern 用 word boundary

const DICT = [
  // ─── Kubernetes 生态 ───
  { topic: 'k8s',           patterns: ['kubernetes', 'k8s', 'kubectl', 'kubelet', '集群编排', 'k8s集群'] },
  { topic: 'scheduler',     patterns: ['scheduler', '调度器', '调度', 'kube-scheduler', 'scheduling framework', 'sched'] },
  { topic: 'informer',      patterns: ['informer', 'reflector', 'lister', 'sharedinformer', 'list-watch', 'list watch'] },
  { topic: 'controller',    patterns: ['controller-manager', 'controller manager', 'reconcile', 'reconciler', '控制器', 'operator pattern'] },
  { topic: 'crd',           patterns: ['crd', 'custom resource', 'customresourcedefinition'] },
  { topic: 'operator',      patterns: ['operator-sdk', 'kubebuilder', 'operator sdk'] },
  { topic: 'apiserver',     patterns: ['apiserver', 'api server', 'kube-apiserver', 'admission webhook', 'aggregation layer'] },
  { topic: 'etcd',          patterns: ['etcd', 'raft', 'mvcc', 'watch event'] },
  { topic: 'cni',           patterns: ['cni', 'cilium', 'calico', 'flannel', 'bpf', 'ebpf'] },
  { topic: 'istio',         patterns: ['istio', 'envoy', 'service mesh', '服务网格'] },
  { topic: 'ingress',       patterns: ['ingress', 'nginx ingress', 'traefik'] },
  { topic: 'helm',          patterns: ['helm', 'chart'] },
  { topic: 'pod',           patterns: ['pod ', 'pod生命周期', 'pod 生命周期', 'sidecar', 'init container'] },
  { topic: 'rbac',          patterns: ['rbac', 'serviceaccount', 'clusterrole'] },
  { topic: 'gpu-scheduling', patterns: ['gpu调度', 'gpu 调度', 'device plugin', 'nvidia gpu', '算力调度'] },

  // ─── Golang 语言 ───
  { topic: 'golang',        patterns: ['golang', 'go语言', 'go 语言'] },
  { topic: 'goroutine',     patterns: ['goroutine', '协程', 'go runtime'] },
  { topic: 'channel',       patterns: ['channel', '通道', 'chan '] },
  { topic: 'gc',            patterns: ['gc', '垃圾回收', 'garbage collect', '三色标记', 'mark and sweep', 'stw'] },
  { topic: 'context',       patterns: ['context', 'context.context', 'ctx', '取消传播'] },
  { topic: 'go-mutex',      patterns: ['sync.mutex', 'rwmutex', '读写锁', 'mutex'] },
  { topic: 'select',        patterns: ['select语句', 'select 语句', 'select case'] },
  { topic: 'go-memory',     patterns: ['内存模型', 'happens-before', 'memory model', 'memory order', '逃逸分析', 'escape analysis'] },
  { topic: 'go-sync',       patterns: ['sync.once', 'sync.pool', 'waitgroup', 'sync.map', 'errgroup'] },
  { topic: 'interface',     patterns: ['interface', '接口', 'iface', 'duck typing'] },
  { topic: 'slice',         patterns: ['slice', '切片', 'append扩容', 'append 扩容'] },
  { topic: 'map',           patterns: ['hashmap', 'hash map', 'go map', 'map扩容'] },
  { topic: 'reflect',       patterns: ['reflect', '反射'] },
  { topic: 'generic',       patterns: ['泛型', 'generic'] },

  // ─── 分布式 / 系统设计 ───
  { topic: 'distributed',   patterns: ['分布式', 'distributed system', '一致性'] },
  { topic: 'raft',          patterns: ['raft'] },
  { topic: 'paxos',         patterns: ['paxos'] },
  { topic: 'cap',           patterns: ['cap理论', 'cap theorem', 'cap 定理'] },
  { topic: 'consistency',   patterns: ['强一致', '最终一致', 'eventual consist', '线性一致', 'linearizability'] },
  { topic: 'lock',          patterns: ['分布式锁', 'distributed lock', 'redlock'] },
  { topic: 'mq',            patterns: ['消息队列', 'kafka', 'rocketmq', 'rabbitmq', 'pulsar', 'message queue'] },
  { topic: 'rpc',           patterns: ['rpc', 'grpc', 'thrift', 'protobuf', '远程调用'] },
  { topic: 'load-balance',  patterns: ['负载均衡', 'load balanc', 'lb', 'consistent hash', '一致性哈希'] },
  { topic: 'cache',         patterns: ['缓存', 'cache', '缓存穿透', '缓存击穿', '缓存雪崩'] },
  { topic: 'rate-limit',    patterns: ['限流', '令牌桶', '漏桶', 'rate limit', 'token bucket'] },
  { topic: 'circuit-breaker', patterns: ['熔断', 'circuit breaker', 'hystrix'] },
  { topic: 'system-design', patterns: ['系统设计', 'system design', '架构设计'] },

  // ─── 数据库 ───
  { topic: 'mysql',         patterns: ['mysql', 'innodb', 'b+树', 'b+ tree', 'btree'] },
  { topic: 'postgres',      patterns: ['postgres', 'pg', 'postgresql'] },
  { topic: 'redis',         patterns: ['redis', 'sds', 'aof', 'rdb', 'cluster mode'] },
  { topic: 'mongodb',       patterns: ['mongodb', 'mongo'] },
  { topic: 'sql',           patterns: ['sql优化', 'sql 优化', 'explain', '慢查询', 'index optimization'] },
  { topic: 'transaction',   patterns: ['事务', 'transaction', 'acid', 'isolation level', '隔离级别'] },
  { topic: 'mvcc',          patterns: ['mvcc', '多版本并发'] },
  { topic: 'sharding',      patterns: ['分库分表', 'sharding', '水平拆分'] },
  { topic: 'replication',   patterns: ['主从复制', 'replication', '主从同步', 'binlog'] },

  // ─── 网络 / 协议 ───
  { topic: 'tcp',           patterns: ['tcp', '三次握手', '四次挥手', 'tcp拥塞', 'congestion'] },
  { topic: 'http',          patterns: ['http/2', 'http2', 'http/3', 'http3', 'http协议', 'http 协议'] },
  { topic: 'tls',           patterns: ['tls', 'ssl', 'https'] },
  { topic: 'websocket',     patterns: ['websocket'] },
  { topic: 'dns',           patterns: ['dns'] },

  // ─── GPU / AI 平台 ───
  { topic: 'gpu',           patterns: ['gpu', 'cuda', 'nvidia', '显存', 'tensor core'] },
  { topic: 'ai-platform',   patterns: ['训练平台', '推理平台', 'mlops', 'ai平台', 'ai 平台'] },
  { topic: 'pytorch',       patterns: ['pytorch'] },
  { topic: 'tensorflow',    patterns: ['tensorflow', 'tf '] },

  // ─── 云 / DevOps ───
  { topic: 'docker',        patterns: ['docker', 'dockerfile', 'oci', 'image registry'] },
  { topic: 'ci-cd',         patterns: ['ci/cd', 'cicd', 'jenkins', 'github actions', 'gitlab ci'] },
  { topic: 'terraform',     patterns: ['terraform'] },
  { topic: 'monitoring',    patterns: ['prometheus', 'grafana', 'metrics', '监控', 'alertmanager'] },
  { topic: 'logging',       patterns: ['elk', 'loki', 'fluentd', '日志收集'] },
  { topic: 'tracing',       patterns: ['jaeger', 'zipkin', 'opentelemetry', 'tracing', '链路追踪'] },

  // ─── 操作系统 / 底层 ───
  { topic: 'os',            patterns: ['操作系统', 'linux内核', 'linux 内核'] },
  { topic: 'memory',        patterns: ['虚拟内存', 'mmap', 'page cache', '页表'] },
  { topic: 'process',       patterns: ['进程', '线程', 'fork', 'exec'] },
  { topic: 'io',            patterns: ['io模型', 'io 模型', 'epoll', 'select io', 'aio'] },
  { topic: 'syscall',       patterns: ['系统调用', 'syscall'] },

  // ─── 算法 ───
  { topic: 'algorithm',     patterns: ['算法', '算法题', 'leetcode'] },
  { topic: 'dp',            patterns: ['动态规划', 'dynamic programming', 'dp'] },
  { topic: 'tree',          patterns: ['二叉树', '树', '红黑树', 'avl'] },
  { topic: 'graph',         patterns: ['图算法', 'graph algorithm', 'bfs', 'dfs'] },
];

// 按 pattern 长度倒序，避免短的吃掉长的
const SORTED_DICT = (() => {
  const expanded = [];
  for (const entry of DICT) {
    for (const p of entry.patterns) {
      expanded.push({ topic: entry.topic, pattern: p, len: p.length });
    }
  }
  expanded.sort((a, b) => b.len - a.len);
  return expanded;
})();

/**
 * 本地匹配技能 topic
 * @param {string} text     题目文本
 * @param {number} maxTopics 最多返回数（默认 6）
 * @returns {string[]} 匹配到的 topic 列表（去重）
 */
export function extractTopicsLocal(text, maxTopics = 6) {
  if (!text) return [];
  const lower = text.toLowerCase();
  const found = new Set();
  for (const { topic, pattern } of SORTED_DICT) {
    if (found.has(topic)) continue;
    if (lower.includes(pattern.toLowerCase())) {
      found.add(topic);
      if (found.size >= maxTopics) break;
    }
  }
  return [...found];
}
