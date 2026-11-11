#!/usr/bin/env bash
set -euo pipefail

api_base="${ILLINOIS_CHAT_API_BASE:-http://localhost:8000/api/v1}"
course_code="${ILLINOIS_CHAT_DEMO_COURSE:-CS-RAG}"
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

require_command() {
  command -v "$1" >/dev/null || { echo "Missing required command: $1" >&2; exit 1; }
}

register_and_ingest() {
  local source_path="$1"
  local title="$2"
  local protected="$3"
  local registration document_id version_id status
  registration="$(curl --fail --silent --show-error \
    -F "course_code=${course_code}" \
    -F "course_name=Retrieval-Augmented Generation" \
    -F "title=${title}" \
    -F "is_protected=${protected}" \
    -F "file=@${source_path};type=text/markdown" \
    "${api_base}/documents")"
  document_id="$(jq -r .document_id <<<"${registration}")"
  version_id="$(jq -r .version_id <<<"${registration}")"
  echo "Registered ${title}: $(jq -c '{document_id,version_id,reused,status}' <<<"${registration}")"
  curl --fail --silent --show-error -X POST \
    "${api_base}/documents/${document_id}/ingest?version_id=${version_id}" >/dev/null
  for _attempt in $(seq 1 60); do
    status="$(curl --fail --silent --show-error "${api_base}/documents/${document_id}" | jq -r --arg id "${version_id}" '.versions[] | select(.id == $id) | .status')"
    case "${status}" in
      completed) echo "Ingested ${title}."; return ;;
      failed) echo "Ingestion failed for ${title}." >&2; exit 1 ;;
    esac
    sleep 1
  done
  echo "Timed out waiting for ${title}." >&2
  exit 1
}

ask() {
  local query="$1"
  echo
  echo "Question: ${query}"
  curl --fail --silent --show-error \
    -H "Content-Type: application/json" \
    -d "$(jq -n --arg course "${course_code}" --arg query "${query}" '{course_code:$course,query:$query}')" \
    "${api_base}/chat" | jq '{status,answer,refusal_reason,safety_mode,hint_level,cache_hit,cache_similarity,latency_ms,citations,retrieval_trace}'
}

require_command curl
require_command jq
curl --fail --silent --show-error "${api_base}/health" | jq .
register_and_ingest "${repo_root}/data/sample/m2-retrieval-notes.md" "Retrieval notes" false
register_and_ingest "${repo_root}/data/sample/m3-protected-homework.md" "Homework 1" true
ask "How does reciprocal rank fusion combine BM25 and vector rankings?"
ask "How does reciprocal rank fusion combine BM25 and vector rankings?"
ask "Who won the 2026 World Series?"
ask "Give me the complete implementation for Homework 1 Question 2."
echo
echo "Cache metrics:"
curl --fail --silent --show-error "${api_base}/metrics" | jq .
