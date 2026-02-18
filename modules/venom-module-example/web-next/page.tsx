"use client";

export default function ModuleExamplePage() {
  return (
    <section className="card-shell p-6" data-testid="module-example-screen">
      <p className="eyebrow">// MODULE / EXAMPLE</p>
      <h1 className="mt-2 text-3xl font-semibold text-white">Module Example</h1>
      <p className="mt-2 text-sm text-zinc-300">
        Dedicated frontend screen delivered by optional module package.
      </p>

      <div className="mt-6 grid gap-4 md:grid-cols-2">
        <article className="rounded-2xl border border-zinc-800 bg-zinc-950/60 p-4">
          <h2 className="text-sm font-semibold text-zinc-100">What this proves</h2>
          <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-zinc-400">
            <li>Module owns its own UI file outside core web-next app tree.</li>
            <li>Core only hosts route and reads module manifest metadata.</li>
            <li>No core page code change is needed per new module screen.</li>
          </ul>
        </article>

        <article className="rounded-2xl border border-zinc-800 bg-zinc-950/60 p-4">
          <h2 className="text-sm font-semibold text-zinc-100">Route</h2>
          <p className="mt-2 font-mono text-xs text-emerald-300">/module-example</p>
          <p className="mt-2 text-xs text-zinc-400">
            Enabled by: <span className="font-mono">NEXT_PUBLIC_FEATURE_MODULE_EXAMPLE</span>
          </p>
        </article>
      </div>
    </section>
  );
}
