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

const POLL_INTERVAL_MS = 2000;

export default function App() {
  const [jobId, setJobId] = useState(null);
  const [videoId, setVideoId] = useState(null);
  const [jobStatus, setJobStatus] = useState(null); // pending | processing | done | error
  const [jobError, setJobError] = useState(null);
  const [results, setResults] = useState(null); // { dialogues, target_matches, duration_sec, ... }
  const [query, setQuery] = useState("");
  const [searchResults, setSearchResults] = useState(null); // null = not searching, show all
  const [activeIndex, setActiveIndex] = useState(null);
  const [modalItem, setModalItem] = useState(null);
  const [formError, setFormError] = useState(null);
  const pollRef = useRef(null);

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  useEffect(() => stopPolling, [stopPolling]);

  async function handleSubmit(url, targetText) {
    setFormError(null);
    setResults(null);
    setSearchResults(null);
    setQuery("");
    setActiveIndex(null);
    stopPolling();

    try {
      const res = await submitVideo(url, targetText);
      setJobId(res.job_id);
      setVideoId(res.video_id);
      setJobStatus(res.status);
      setJobError(null);

      pollRef.current = setInterval(async () => {
        try {
          const s = await getJobStatus(res.job_id);
          setJobStatus(s.status);
          setJobError(s.error);
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
      }, POLL_INTERVAL_MS);
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

  const latestTargetMatch = results?.target_matches?.[0]
    ? {
        ...results.target_matches[0],
        frame_url: frameSrc(results.target_matches[0].frame_url),
      }
    : null;

  function openFrame(item) {
    setModalItem(item);
    if (typeof item.index === "number") setActiveIndex(item.index);
  }

  return (
    <div className="min-h-screen">
      <Header />

      <main className="max-w-5xl mx-auto px-6 py-8 space-y-6">
        <VideoForm onSubmit={handleSubmit} disabled={isBusy} />

        {formError && (
          <div className="border border-miss/40 bg-miss/10 rounded-lg px-4 py-3 text-sm text-neutral-200">
            {formError}
          </div>
        )}

        {jobStatus && <StatusBanner status={jobStatus} error={jobError} />}

        {latestTargetMatch && (
          <TargetMatchCard match={latestTargetMatch} onOpenFrame={openFrame} />
        )}

        {results && allDialogues.length > 0 && (
          <>
            <Timeline
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

            <section className="space-y-3">
              <SearchBar onQueryChange={onQueryChange} count={shownDialogues.length} />
              <DialogueList
                dialogues={shownDialogues}
                activeIndex={activeIndex}
                onOpenFrame={openFrame}
              />
            </section>
          </>
        )}

        {results && allDialogues.length === 0 && (
          <div className="text-center py-12 border border-dashed border-base-700 rounded-lg">
            <p className="text-sm text-neutral-500">
              No on-screen dialogue was detected in this video.
            </p>
          </div>
        )}
      </main>

      <FrameModal item={modalItem} onClose={() => setModalItem(null)} />
    </div>
  );
}
