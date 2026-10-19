"""Starter questions per technology for the tech-stack interview.

The planner sees these as calibration ("this is the depth we want") and may
reuse or go beyond them; they're also the fallback when planning fails. Topics
not listed here still work — the model writes their questions from scratch.
A question may carry a code snippet, shown on screen (never read aloud).
"""

BANK: dict[str, list[dict]] = {
    "react": [
        {"question": "Walk me through what happens between calling a state setter and the screen updating. Where do reconciliation and batching come in?"},
        {"question": "What's wrong with this component, and how would you fix it?",
         "code": "function Search({ query }) {\n  const [results, setResults] = useState([]);\n  useEffect(() => {\n    fetch(`/api?q=${query}`)\n      .then(r => r.json())\n      .then(setResults);\n  });\n  return <List items={results} />;\n}",
         "language": "jsx"},
        {"question": "A list of ten thousand rows lags on every keystroke in a filter box. How do you find the cause and fix it?"},
        {"question": "When would you reach for useMemo, useCallback or React.memo, and when do they make things worse?"},
    ],
    "javascript": [
        {"question": "What does this print, and why?",
         "code": "console.log('A');\nsetTimeout(() => console.log('B'), 0);\nPromise.resolve().then(() => console.log('C'));\nconsole.log('D');",
         "language": "javascript"},
        {"question": "Explain closures with a real bug they cause, and how you'd fix it."},
        {"question": "How does `this` get its value? Walk me through the four or five cases."},
        {"question": "What's the difference between == and ===, and between null and undefined, and when does it bite in practice?"},
    ],
    "typescript": [
        {"question": "When would you use unknown instead of any, and how do you narrow it safely?"},
        {"question": "Explain structural typing. What surprising thing can it let through?"},
        {"question": "How would you type a function that takes an object and a key and returns the value at that key?"},
    ],
    "node.js": [
        {"question": "Explain the Node event loop. What happens to your API's latency if one request runs a CPU-heavy loop for two seconds?"},
        {"question": "How do you handle errors in an Express or Fastify app so one bad request can't crash the process?"},
        {"question": "Streams versus reading a whole file into memory: when does it matter, and how does backpressure work?"},
    ],
    "python": [
        {"question": "What does this print, and why?",
         "code": "def add(item, bucket=[]):\n    bucket.append(item)\n    return bucket\n\nprint(add(1))\nprint(add(2))",
         "language": "python"},
        {"question": "Explain the GIL. When do you use threads, processes or asyncio?"},
        {"question": "How do generators work, and when would you choose one over building a list?"},
        {"question": "How would you find and fix a memory leak in a long-running Python service?"},
    ],
    "java": [
        {"question": "Explain how HashMap works internally, and what happens when two keys collide."},
        {"question": "What's the difference between checked and unchecked exceptions, and how do you decide which to throw?"},
        {"question": "How would you make this class thread-safe, and what are your options?",
         "code": "public class Counter {\n    private int count = 0;\n    public void increment() { count++; }\n    public int get() { return count; }\n}",
         "language": "java"},
    ],
    "spring boot": [
        {"question": "Walk me through what happens from an HTTP request arriving to your controller method being called."},
        {"question": "How does @Transactional work under the hood, and when does it silently not apply?"},
        {"question": "How do you design idempotent POST endpoints so retries don't create duplicates?"},
    ],
    "sql": [
        {"question": "This query is slow on a ten-million-row table. How do you investigate and speed it up?",
         "code": "SELECT *\nFROM orders\nWHERE LOWER(customer_email) = 'a@b.com'\nORDER BY created_at DESC\nLIMIT 20;",
         "language": "sql"},
        {"question": "Explain the difference between INNER, LEFT and a correlated subquery, with a case for each."},
        {"question": "What are transaction isolation levels, and what anomaly does each one prevent?"},
        {"question": "When would you denormalize a schema on purpose?"},
    ],
    "docker": [
        {"question": "How do you keep a Docker image small and builds fast? Talk about layers and caching."},
        {"question": "What's the difference between an image and a container, and between CMD and ENTRYPOINT?"},
        {"question": "Your container works locally but crashes in production. How do you debug it?"},
    ],
    "kubernetes": [
        {"question": "Explain how a request reaches a pod: Services, Ingress and kube-proxy."},
        {"question": "Your pods keep restarting with CrashLoopBackOff. Walk me through debugging it."},
        {"question": "What's the difference between liveness and readiness probes, and what goes wrong if you mix them up?"},
    ],
    "aws": [
        {"question": "Design a simple, highly available setup for a web API on AWS. Which services and why?"},
        {"question": "How do IAM roles differ from users, and how should an EC2 or Lambda workload get credentials?"},
        {"question": "When would you choose SQS, SNS or EventBridge?"},
    ],
}

_ALIASES = {"reactjs": "react", "react.js": "react", "js": "javascript", "ts": "typescript", "node": "node.js",
            "nodejs": "node.js", "springboot": "spring boot", "spring": "spring boot", "postgresql": "sql",
            "postgres": "sql", "mysql": "sql", "k8s": "kubernetes", "amazon web services": "aws"}


def seeds(topic: str) -> list[dict]:
    key = topic.strip().lower()
    return BANK.get(_ALIASES.get(key, key), [])
