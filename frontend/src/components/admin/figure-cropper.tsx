"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { SelectionRect } from "@/lib/image";
import { FigureSource } from "@/types/figure";

type HandleId = "nw" | "ne" | "sw" | "se";
type DragState =
  | { mode: "create"; origin: { x: number; y: number } }
  | { mode: "resize"; handle: HandleId; startRect: SelectionRect }
  | null;

export type FigureCropperProps = {
  source: FigureSource;
  selection: SelectionRect | null;
  zoom: number;
  onSelectionChange: (rect: SelectionRect | null) => void;
  onSelectionComplete: (rect: SelectionRect | null) => void;
  onZoomChange: (value: number) => void;
};

const clamp = (value: number, min: number, max: number) => Math.min(Math.max(value, min), max);

export function FigureCropper({
  source,
  selection,
  zoom,
  onSelectionChange,
  onSelectionComplete,
  onZoomChange,
}: FigureCropperProps) {
  const overlayRef = useRef<HTMLDivElement>(null);
  const dragState = useRef<DragState>(null);
  const activePointerId = useRef<number | null>(null);
  const [internalSelection, setInternalSelection] = useState<SelectionRect | null>(selection);
  const baseZoomRef = useRef(zoom);

  useEffect(() => {
    setInternalSelection(selection);
  }, [selection]);

  const updateSelection = useCallback(
    (rect: SelectionRect | null) => {
      setInternalSelection(rect);
      onSelectionChange(rect);
    },
    [onSelectionChange]
  );

  const clientToSource = useCallback(
    (clientX: number, clientY: number) => {
      const overlay = overlayRef.current;
      if (!overlay) return null;
      const rect = overlay.getBoundingClientRect();
      if (rect.width === 0 || rect.height === 0) return null;
      const x = clamp(((clientX - rect.left) / rect.width) * source.width, 0, source.width);
      const y = clamp(((clientY - rect.top) / rect.height) * source.height, 0, source.height);
      return { x, y };
    },
    [source.height, source.width]
  );

  const normalizeRect = useCallback(
    (x1: number, y1: number, x2: number, y2: number): SelectionRect => {
      const left = clamp(Math.min(x1, x2), 0, source.width);
      const right = clamp(Math.max(x1, x2), 0, source.width);
      const top = clamp(Math.min(y1, y2), 0, source.height);
      const bottom = clamp(Math.max(y1, y2), 0, source.height);
      return {
        x: left,
        y: top,
        width: Math.max(1, right - left),
        height: Math.max(1, bottom - top),
      };
    },
    [source.height, source.width]
  );

  const resizeFromHandle = useCallback(
    (rect: SelectionRect, handle: HandleId, point: { x: number; y: number }) => {
      const left = rect.x;
      const top = rect.y;
      const right = rect.x + rect.width;
      const bottom = rect.y + rect.height;
      switch (handle) {
        case "nw":
          return normalizeRect(point.x, point.y, right, bottom);
        case "ne":
          return normalizeRect(left, point.y, point.x, bottom);
        case "sw":
          return normalizeRect(point.x, top, right, point.y);
        case "se":
        default:
          return normalizeRect(left, top, point.x, point.y);
      }
    },
    [normalizeRect]
  );

  const handlePointerMove = useCallback(
    (event: React.PointerEvent<HTMLDivElement>) => {
      if (activePointerId.current !== event.pointerId) return;
      const state = dragState.current;
      if (!state) return;
      const point = clientToSource(event.clientX, event.clientY);
      if (!point) return;
      if (state.mode === "create") {
        updateSelection(normalizeRect(state.origin.x, state.origin.y, point.x, point.y));
      } else if (state.mode === "resize") {
        updateSelection(resizeFromHandle(state.startRect, state.handle, point));
      }
    },
    [clientToSource, normalizeRect, resizeFromHandle, updateSelection]
  );

  const handlePointerDown = useCallback(
    (event: React.PointerEvent<HTMLDivElement>) => {
      if (event.pointerType === "touch") {
        const overlay = event.currentTarget;
        overlay.releasePointerCapture(event.pointerId);
        return;
      }
      event.preventDefault();
      const point = clientToSource(event.clientX, event.clientY);
      if (!point) return;
      const target = event.target as HTMLElement;
      const handleId = (target?.dataset?.handle as HandleId | undefined) || undefined;
      const overlay = event.currentTarget;
      overlay.setPointerCapture(event.pointerId);
      activePointerId.current = event.pointerId;
      if (handleId && internalSelection) {
        dragState.current = { mode: "resize", handle: handleId, startRect: internalSelection };
        return;
      }
      dragState.current = { mode: "create", origin: point };
      updateSelection({ x: point.x, y: point.y, width: 1, height: 1 });
    },
    [clientToSource, internalSelection, updateSelection]
  );

  const handlePointerUp = useCallback(
    (event: React.PointerEvent<HTMLDivElement>) => {
      if (activePointerId.current !== event.pointerId) return;
      activePointerId.current = null;
      const overlay = event.currentTarget;
      try {
        overlay.releasePointerCapture(event.pointerId);
      } catch {
        /* noop */
      }
      dragState.current = null;
      onSelectionComplete(internalSelection);
    },
    [internalSelection, onSelectionComplete]
  );

  const handleWheel = useCallback(
    (event: React.WheelEvent<HTMLDivElement>) => {
      if (!event.ctrlKey) return;
      event.preventDefault();
      const delta = -event.deltaY;
      const scaleChange = delta > 0 ? 0.05 : -0.05;
      const newZoom = clamp(zoom + scaleChange, 0.8, 2.5);
      baseZoomRef.current = newZoom;
      onZoomChange(newZoom);
    },
    [zoom, onZoomChange]
  );

  const BASE_WIDTH = 720;
  const BASE_HEIGHT = 520;
  const baseScale = Math.min(BASE_WIDTH / source.width, BASE_HEIGHT / source.height);
  const safeBaseScale = Number.isFinite(baseScale) && baseScale > 0 ? baseScale : 1;
  const rawWidth = source.width * safeBaseScale * zoom;
  const rawHeight = source.height * safeBaseScale * zoom;
  const clampScale = Math.min(
    1,
    BASE_WIDTH / Math.max(rawWidth, 1),
    BASE_HEIGHT / Math.max(rawHeight, 1)
  );
  const displayWidth = rawWidth * clampScale;
  const displayHeight = rawHeight * clampScale;
  const effectiveScale = safeBaseScale * zoom * clampScale;

  const selectionStyle = useMemo(() => {
    if (!internalSelection) return null;
    const width = internalSelection.width * effectiveScale;
    const height = internalSelection.height * effectiveScale;
    const left = internalSelection.x * effectiveScale;
    const top = internalSelection.y * effectiveScale;
    return { width, height, left, top };
  }, [internalSelection, effectiveScale]);

  const handleOffsets: Record<HandleId, { left: number; top: number; cursor: string }> = {
    nw: { left: -6, top: -6, cursor: "nwse-resize" },
    ne: { left: selectionStyle ? selectionStyle.width - 6 : -6, top: -6, cursor: "nesw-resize" },
    sw: { left: -6, top: selectionStyle ? selectionStyle.height - 6 : -6, cursor: "nesw-resize" },
    se: {
      left: selectionStyle ? selectionStyle.width - 6 : -6,
      top: selectionStyle ? selectionStyle.height - 6 : -6,
      cursor: "nwse-resize",
    },
  };

  return (
    <div className="flex justify-center">
      <div
        className="relative inline-block rounded-xl bg-[#0f172a] p-2"
        style={{ width: displayWidth + 16 }}
      >
        <div className="relative inline-block rounded-xl bg-white shadow-2xl">
          <img
            src={source.image}
            alt={`PDF page ${source.page}`}
            className="select-none rounded-xl"
            draggable={false}
            style={{ width: displayWidth, height: displayHeight }}
          />
          <div
            ref={overlayRef}
            className="absolute inset-0 cursor-crosshair rounded-xl"
            onPointerDown={handlePointerDown}
            onPointerMove={handlePointerMove}
            onPointerUp={handlePointerUp}
            onWheel={handleWheel}
          >
            {internalSelection && selectionStyle && (
              <div
                className="absolute border-2 border-sky-300 bg-sky-300/25 backdrop-brightness-150"
                style={selectionStyle}
              >
                {(Object.keys(handleOffsets) as HandleId[]).map((handle) => (
                  <div
                    key={handle}
                    data-handle={handle}
                    className="absolute h-3 w-3 rounded-full border border-white bg-sky-400 shadow"
                    style={{
                      left: handleOffsets[handle].left,
                      top: handleOffsets[handle].top,
                      cursor: handleOffsets[handle].cursor,
                    }}
                  />
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

