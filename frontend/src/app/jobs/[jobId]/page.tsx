import type { Metadata } from "next";

import { JobTracker } from "@/components/job/job-tracker";

export const metadata: Metadata = { title: "Your song — Tunora" };

export default async function JobPage({ params }: PageProps<"/jobs/[jobId]">) {
  const { jobId } = await params;

  return (
    <div className="mx-auto w-full max-w-3xl px-4 py-8 sm:px-6 sm:py-12">
      <JobTracker jobId={jobId} />
    </div>
  );
}
