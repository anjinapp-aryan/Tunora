import type { Metadata } from "next";

import { ProjectDetailsView } from "@/components/projects/project-details";

export const metadata: Metadata = { title: "Project — Tunora" };

export default async function ProjectPage({ params }: PageProps<"/projects/[projectId]">) {
  const { projectId } = await params;

  return (
    <div className="mx-auto w-full max-w-3xl px-4 py-8 sm:px-6 sm:py-12">
      <ProjectDetailsView projectId={projectId} />
    </div>
  );
}
