import DialogueCard from "./DialogueCard.jsx";

export default function DialogueList({ dialogues, activeIndex, onOpenFrame }) {
  if (!dialogues.length) {
    return (
      <div className="text-center py-12 border border-dashed border-base-700 rounded-lg">
        <p className="text-sm text-neutral-500">No dialogue matches that search.</p>
      </div>
    );
  }

  return (
    <ul className="space-y-2.5">
      {dialogues.map((d) => (
        <DialogueCard
          key={d.index}
          dialogue={d}
          active={d.index === activeIndex}
          onOpenFrame={onOpenFrame}
        />
      ))}
    </ul>
  );
}
