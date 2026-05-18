import Doc from "../../content/walking-distance.mdx";

export default function Methodology() {
  return (
    <div className="h-full w-full overflow-y-auto bg-white">
      <article className="prose prose-zinc max-w-3xl mx-auto px-6 py-10 prose-headings:scroll-mt-20 prose-table:text-sm prose-code:before:content-none prose-code:after:content-none prose-code:bg-zinc-100 prose-code:px-1 prose-code:py-0.5 prose-code:rounded">
        <Doc />
      </article>
    </div>
  );
}
