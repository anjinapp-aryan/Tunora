import type { Metadata } from "next";

import { ProjectList } from "@/components/projects/project-list";

export const metadata: Metadata = { title: "Projects — Tunora" };

export default function ProjectsPage() {
  return (
    <div className="mx-auto w-full max-w-3xl px-4 py-8 sm:px-6 sm:py-12">
      <div className="mb-8">
        <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">Projects</h1>
        <p className="mt-2 text-sm text-muted-foreground">Group your songs into creative workspaces, like an album or a soundtrack.</p>
      </div>
      <ProjectList />
    </div>
  );
}
