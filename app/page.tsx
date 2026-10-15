import Link from "next/link";
import MotionStudy from "@/app/components/motion-study";
import { redirect } from "next/navigation";

export default async function Home({ searchParams }: { searchParams: Promise<{ job?: string }> }) {
  const { job } = await searchParams;
  // Keep existing saved video links working after the studio moves.
  if (job && /^[a-f0-9]{32}$/.test(job)) redirect(`/studio?job=${job}`);
  return (
    <main className="landing-main" id="main">
      <section className="landing-hero" aria-labelledby="hero-title">
        <div className="hero-copy">
          <h1 id="hero-title">Ideas, made<br />visible.</h1>
          <p>Turn what you want to explain into a short animation.</p>
          <Link className="primary-button hero-button" href="/studio">Create your first video</Link>
        </div>
        <div className="hero-visual"><MotionStudy /></div>
      </section>
      <section className="landing-bottom" aria-label="How Forma works">
        <p>Less explaining.<br /><span>More understanding.</span></p>
        <ol className="landing-process"><li><span aria-hidden="true">1</span>Describe an idea</li><li><span aria-hidden="true">2</span>Create a video</li><li><span aria-hidden="true">3</span>Watch and share</li></ol>
      </section>
      <footer className="landing-footer"><span>Forma</span><span>For the things words alone can&apos;t explain.</span></footer>
    </main>
  );
}
