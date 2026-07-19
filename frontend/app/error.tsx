"use client";

// Route-segment error boundary. A render/runtime crash in any page renders
// this recovery card instead of white-screening the app. `reset()` re-renders
// the segment without a full reload.
export default function RouteError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  return (
    <div className="flex items-center justify-center min-h-[60vh] p-6">
      <div className="panel max-w-md w-full text-center">
        <div className="text-[0.65rem] uppercase tracking-[0.14em] text-danger font-bold">
          Something went wrong
        </div>
        <h2 className="m-0 text-xl font-bold mt-1">This view hit an error</h2>
        <p className="text-sm text-muted mt-2">
          The rest of the app is fine — only this screen failed to render. Try again, or
          head back to the overview.
        </p>
        {error?.message ? (
          <pre className="text-left text-[0.7rem] text-muted bg-white/[0.03] rounded-lg p-3 mt-3 overflow-x-auto whitespace-pre-wrap">
            {error.message}
            {error.digest ? `\n\ndigest: ${error.digest}` : ""}
          </pre>
        ) : null}
        <div className="flex gap-2 justify-center mt-4">
          <button className="btn btn-primary" onClick={() => reset()}>
            Try again
          </button>
          <a className="btn btn-secondary" href="/overview">
            Go to overview
          </a>
        </div>
      </div>
    </div>
  );
}
