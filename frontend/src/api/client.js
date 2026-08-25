const BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

async function request(path, options = {}) {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch {
      // response wasn't JSON, keep statusText
    }
    throw new Error(detail);
  }
  return res.json();
}

/** POST /videos/process -- kicks off async processing, returns {job_id, video_id, status}
 *  scanAll=false (default): stop at the first dialogue.
 *  scanAll=true: collect every distinct on-screen dialogue frame.
 */
export function submitVideo(url, targetText, force = false, scanAll = false) {
  return request("/videos/process", {
    method: "POST",
    body: JSON.stringify({
      url,
      target_text: targetText || null,
      force,
      scan_all: scanAll,
    }),
  });
}

/** GET /videos/{job_id}/status */
export function getJobStatus(jobId) {
  return request(`/videos/${encodeURIComponent(jobId)}/status`);
}

/** GET /videos/{video_id}/results */
export function getResults(videoId) {
  return request(`/videos/${encodeURIComponent(videoId)}/results`);
}

/** GET /videos/{video_id}/search?q=... */
export function searchDialogues(videoId, query) {
  return request(
    `/videos/${encodeURIComponent(videoId)}/search?q=${encodeURIComponent(query)}`
  );
}

export function frameSrc(url) {
  if (!url) return null;
  return url.startsWith("http") ? url : `${BASE_URL}${url}`;
}

export { BASE_URL };
