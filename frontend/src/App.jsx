import { useCallback, useEffect, useRef, useState } from "react";
import Header from "./components/Header.jsx";
import VideoForm from "./components/VideoForm.jsx";
import StatusBanner from "./components/StatusBanner.jsx";
import TargetMatchCard from "./components/TargetMatchCard.jsx";
import Timeline from "./components/Timeline.jsx";
import SearchBar from "./components/SearchBar.jsx";
import DialogueList from "./components/DialogueList.jsx";
import FrameModal from "./components/FrameModal.jsx";
import { submitVideo, getJobStatus, getResults, searchDialogues, frameSrc } from "./api/client.js";

export default function App() {
  const [videoId, setVideoId] = useState(null);
  const [jobStatus, setJobStatus] = useState(null); // pending | processing | done | error
  const [jobError, setJobError] = useState(null);
  const [jobStage, setJobStage] = useState(null);
  const [jobMessage, setJobMessage] = useState(null);
  const [jobProgress, setJobProgress] = useState(null);
  const [results, setResults] = useState(null); // { dialogues, target_matches, duration_sec, ... }
  const [query, setQuery] = useState("");
  const [searchResults, setSearchResults] = useState(null); // null = not searching, show all
  const [activeIndex, setActiveIndex] = useState(null);
  const [modalItem, setModalItem] = useState(null);
  const [jobCached, setJobCached] = useState(false);
  const [formError, setFormError] = useState(null);
  const [submittedTarget, setSubmittedTarget] = useState("");
  const pollRef = useRef(null);

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  useEffect(() => stopPolling, [stopPolling]);

  async function handleSubmit(url, targetText, scanAll = false) {
    setFormError(null);
    setResults(null);
    setSearchResults(null);
    setQuery("");
    setActiveIndex(null);
    setJobStage(null);
    setJobMessage(null);
    setJobProgress(null);
    setJobCached(false);
    setSubmittedTarget(targetText || "");
    stopPolling();

    try {
      const res = await submitVideo(url, targetText, false, scanAll);
      setVideoId(res.video_id);
      setJobStatus(res.status);
      setJobError(null);
      setJobCached(Boolean(res.cached));

      if (res.status === "done") {
        setJobStage("done");
        setJobMessage(
          res.cached
            ? "Cache hit — same video and dialogue already processed"
            : "Finished"
        );
        setJobProgress(1);
        const r = await getResults(res.video_id);
        setResults(r);
        return;
      }

      pollRef.current = setInterval(async () => {
        try {
          const s = await getJobStatus(res.job_id);
          setJobStatus(s.status);
          setJobError(s.error);
          setJobStage(s.stage ?? null);
          setJobMessage(s.message ?? null);
          setJobProgress(typeof s.progress === "number" ? s.progress : null);
          setJobCached(Boolean(s.cached));
          if (s.status === "done") {
            stopPolling();
            const r = await getResults(s.video_id || res.video_id);
            setResults(r);
          } else if (s.status === "error") {
            stopPolling();
          }
        } catch (err) {
          setJobError(err.message);
          setJobStatus("error");
          stopPolling();
        }
      }, 1000);
    } catch (err) {
      setFormError(err.message);
    }
  }

  const onQueryChange = useCallback(
    async (q) => {
      setQuery(q);
      if (!videoId || !q) {
        setSearchResults(null);
        return;
      }
      try {
        const res = await searchDialogues(videoId, q);
        setSearchResults(res.results);
      } catch {
        setSearchResults([]);
      }
    },
    [videoId]
  );

  const isBusy = jobStatus === "pending" || jobStatus === "processing";
  const allDialogues = results?.dialogues ?? [];
  const shownDialogues = (searchResults ?? allDialogues).map((d) => ({
    ...d,
    frame_url: d.frame_url ? frameSrc(d.frame_url) : d.frame_url,
  }));

  const wanted = (submittedTarget || "").trim().toLowerCase();
  const rawMatch =
    (wanted
      ? results?.target_matches?.find(
          (t) => (t.target_text || "").trim().toLowerCase() === wanted
        )
      : null) || results?.target_matches?.[0];
  const latestTargetMatch = rawMatch
    ? {
        ...rawMatch,
        frame_url: frameSrc(rawMatch.frame_url),
      }
    : null;

  function openFrame(item) {
    setModalItem(item);
    if (typeof item.index === "number") setActiveIndex(item.index);
  }

  return (
    <div className="min-h-screen">
      <Header />

      <main className="max-w-6xl mx-auto px-6 lg:px-8 py-10 space-y-7">
        <VideoForm onSubmit={handleSubmit} disabled={isBusy} />

        {formError && (
          <div className="border border-miss/40 bg-miss/10 rounded-lg px-4 py-3 text-sm text-neutral-200">
            {formError}
          </div>
        )}

        {jobStatus && (
          <StatusBanner
            status={jobStatus}
            error={jobError}
            stage={jobStage}
            message={jobMessage}
            progress={jobProgress}
            cached={jobCached}
          />
        )}

        {latestTargetMatch && (
          <TargetMatchCard match={latestTargetMatch} onOpenFrame={openFrame} />
        )}

        {/* Full dialogue list / timeline only when the user opted into scan-all
            (or when more than one line was returned). First-dialogue-only runs
            surface the answer via TargetMatchCard above. */}
        {results && allDialogues.length > 1 && (
          <>
            <Timeline
              id="timeline"
              dialogues={allDialogues}
              duration={results.duration_sec}
              activeIndex={activeIndex}
              onSelect={(idx) => {
                setActiveIndex(idx);
                document
                  .getElementById(`dialogue-${idx}`)
                  ?.scrollIntoView({ behavior: "smooth", block: "center" });
              }}
            />

            <section id="results" className="space-y-3">
              <SearchBar onQueryChange={onQueryChange} count={shownDialogues.length} />
              <DialogueList
                dialogues={shownDialogues}
                activeIndex={activeIndex}
                onOpenFrame={openFrame}
              />
            </section>
          </>
        )}

        {results && allDialogues.length === 1 && !latestTargetMatch && (
          <section id="results" className="space-y-3">
            <DialogueList
              dialogues={shownDialogues}
              activeIndex={activeIndex}
              onOpenFrame={openFrame}
            />
          </section>
        )}

        {results && allDialogues.length === 0 && !latestTargetMatch && (
          <div className="text-center py-12 border border-dashed border-base-700 rounded-lg">
            <p className="text-sm text-neutral-500">
              No on-screen dialogue was detected in this video.
            </p>
          </div>
        )}
      </main>

      <FrameModal item={modalItem} onClose={() => setModalItem(null)} />

      <footer className="max-w-6xl mx-auto px-6 lg:px-8 py-6 border-t border-base-800">
        <p className="font-mono text-xs text-neutral-700 tracking-widest">
          v.2026.08 · frame-finder · locate the frame, not just the line
        </p>
      </footer>
    </div>
  );
}