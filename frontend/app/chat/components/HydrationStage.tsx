export function HydrationStage({ theme }: { theme: string }) {
  return (
    <main className="chat-shell" data-theme={theme}>
      <section className="hydration-stage" aria-live="polite">
        <div className="hydration-loader">
          <span aria-hidden="true" />
          <p>Loading</p>
        </div>
      </section>
    </main>
  );
}
