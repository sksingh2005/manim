import type { Metadata } from "next";
import VideoWorkspace from "@/app/video-workspace";

export const metadata: Metadata = { title: "Studio" };

export default function Studio() {
  return <VideoWorkspace />;
}
