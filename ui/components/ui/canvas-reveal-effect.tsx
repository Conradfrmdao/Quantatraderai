'use client';

import React, { useEffect, useRef } from "react";

const VERTEX_SHADER = `
attribute vec2 a_position;
attribute vec2 a_texcoord;
varying vec2 v_uv;
void main() {
  v_uv = a_texcoord;
  gl_Position = vec4(a_position, 0.0, 1.0);
}
`;

const FRAGMENT_SHADER = `
precision mediump float;
varying vec2 v_uv;
uniform float u_time;
uniform float u_reveal;
uniform vec2  u_resolution;

float hash(vec2 p) {
  return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453123);
}

void main() {
  vec2 uv = v_uv;
  float cols = 60.0;
  float rows = 60.0 * (u_resolution.y / u_resolution.x);

  vec2 gridUv  = uv * vec2(cols, rows);
  vec2 cell    = floor(gridUv);
  vec2 cellUv  = fract(gridUv) - 0.5;

  float rnd       = hash(cell);
  float revealAt  = rnd * 0.6;
  float progress  = smoothstep(revealAt, revealAt + 0.3, u_reveal);

  float flicker = 0.75 + 0.25 * sin(u_time * (1.0 + rnd * 3.0) + rnd * 6.28);
  float radius  = 0.18;
  float d       = length(cellUv);
  float dot     = (1.0 - smoothstep(radius * 0.7, radius, d)) * progress * flicker;

  float vignette = 1.0 - smoothstep(0.25, 0.65, length(uv - 0.5));
  float dim       = 0.25 + 0.75 * rnd;

  vec3 col = vec3(1.0) * dot * dim * vignette;
  gl_FragColor  = vec4(col, dot * dim * vignette * 0.65);
}
`;

function createShader(gl: WebGLRenderingContext, type: number, src: string) {
  const s = gl.createShader(type)!;
  gl.shaderSource(s, src);
  gl.compileShader(s);
  return s;
}

function createProgram(gl: WebGLRenderingContext) {
  const vs = createShader(gl, gl.VERTEX_SHADER,   VERTEX_SHADER);
  const fs = createShader(gl, gl.FRAGMENT_SHADER, FRAGMENT_SHADER);
  const p  = gl.createProgram()!;
  gl.attachShader(p, vs);
  gl.attachShader(p, fs);
  gl.linkProgram(p);
  return p;
}

interface Props {
  className?: string;
  revealDuration?: number; // seconds for dots to fully appear
}

export function CanvasRevealEffect({ className = "", revealDuration = 2.5 }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const rafRef    = useRef<number>(0);
  const startRef  = useRef<number>(0);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const gl = canvas.getContext("webgl", { alpha: true, premultipliedAlpha: false });
    if (!gl) return;

    const prog = createProgram(gl);
    gl.useProgram(prog);

    // Full-screen quad
    const positions = new Float32Array([-1,-1, 1,-1, -1,1, 1,1]);
    const texcoords = new Float32Array([ 0, 0, 1, 0,  0,1, 1,1]);

    const posBuf = gl.createBuffer()!;
    gl.bindBuffer(gl.ARRAY_BUFFER, posBuf);
    gl.bufferData(gl.ARRAY_BUFFER, positions, gl.STATIC_DRAW);
    const posLoc = gl.getAttribLocation(prog, "a_position");
    gl.enableVertexAttribArray(posLoc);
    gl.vertexAttribPointer(posLoc, 2, gl.FLOAT, false, 0, 0);

    const texBuf = gl.createBuffer()!;
    gl.bindBuffer(gl.ARRAY_BUFFER, texBuf);
    gl.bufferData(gl.ARRAY_BUFFER, texcoords, gl.STATIC_DRAW);
    const texLoc = gl.getAttribLocation(prog, "a_texcoord");
    gl.enableVertexAttribArray(texLoc);
    gl.vertexAttribPointer(texLoc, 2, gl.FLOAT, false, 0, 0);

    const uTime    = gl.getUniformLocation(prog, "u_time");
    const uReveal  = gl.getUniformLocation(prog, "u_reveal");
    const uRes     = gl.getUniformLocation(prog, "u_resolution");

    gl.enable(gl.BLEND);
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);

    const resize = () => {
      canvas.width  = canvas.offsetWidth  * window.devicePixelRatio;
      canvas.height = canvas.offsetHeight * window.devicePixelRatio;
      gl.viewport(0, 0, canvas.width, canvas.height);
    };
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(canvas);

    startRef.current = performance.now();

    const tick = (now: number) => {
      const elapsed = (now - startRef.current) / 1000;
      const reveal  = Math.min(elapsed / revealDuration, 1.0);

      gl.clearColor(0, 0, 0, 0);
      gl.clear(gl.COLOR_BUFFER_BIT);

      gl.uniform1f(uTime,   elapsed);
      gl.uniform1f(uReveal, reveal);
      gl.uniform2f(uRes,    canvas.width, canvas.height);

      gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
      rafRef.current = requestAnimationFrame(tick);
    };
    rafRef.current = requestAnimationFrame(tick);

    return () => {
      cancelAnimationFrame(rafRef.current);
      ro.disconnect();
    };
  }, [revealDuration]);

  return (
    <canvas
      ref={canvasRef}
      className={className}
      style={{ width: "100%", height: "100%", display: "block" }}
    />
  );
}
