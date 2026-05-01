'use client';

import { useEffect, useRef } from 'react';

const NODE_COUNT     = 90;
const CONNECTION_PX  = 240;   // max px distance to draw an edge
const FOCAL          = 460;   // lower = more dramatic perspective spread

interface Node {
  x: number; y: number; z: number;
  vx: number; vy: number; vz: number;
  r: number;          // base radius
  phase: number;      // pulsing phase offset
  big: boolean;       // "agent" node — glows
}

function project(x: number, y: number, z: number, W: number, H: number) {
  const s = FOCAL / (FOCAL + z + 200);
  return { px: W / 2 + x * s, py: H / 2 + y * s, scale: s };
}

export function NeuralBackground({ className = '' }: { className?: string }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const mouse     = useRef({ x: 0, y: 0 });
  const raf       = useRef(0);
  const t0        = useRef(0);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d')!;

    // Spawn nodes evenly over a sphere shell
    const nodes: Node[] = Array.from({ length: NODE_COUNT }, () => {
      const theta = Math.random() * Math.PI * 2;
      const phi   = Math.acos(2 * Math.random() - 1);
      const rad   = 240 + Math.random() * 200;   // much larger sphere
      const big   = Math.random() < 0.14;
      return {
        x: rad * Math.sin(phi) * Math.cos(theta),
        y: rad * Math.sin(phi) * Math.sin(theta),
        z: rad * Math.cos(phi),
        vx: (Math.random() - 0.5) * 0.25,
        vy: (Math.random() - 0.5) * 0.25,
        vz: (Math.random() - 0.5) * 0.25,
        r: big ? 4.5 + Math.random() * 2 : 1.2 + Math.random() * 2,
        phase: Math.random() * Math.PI * 2,
        big,
      };
    });

    const resize = () => {
      canvas.width  = canvas.offsetWidth  * window.devicePixelRatio;
      canvas.height = canvas.offsetHeight * window.devicePixelRatio;
    };
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(canvas);

    const onMove = (e: MouseEvent) => {
      mouse.current = { x: e.clientX - window.innerWidth  / 2,
                        y: e.clientY - window.innerHeight / 2 };
    };
    window.addEventListener('mousemove', onMove);
    t0.current = performance.now();

    const tick = (now: number) => {
      const elapsed = (now - t0.current) / 1000;
      const W = canvas.width, H = canvas.height;
      ctx.clearRect(0, 0, W, H);

      // Slow auto-rotation + subtle mouse parallax
      const rotY  = elapsed * 0.07;
      const tilX  = (mouse.current.x / (window.innerWidth  / 2)) * 0.10;
      const tilY  = (mouse.current.y / (window.innerHeight / 2)) * 0.10;
      const cosY  = Math.cos(rotY),  sinY  = Math.sin(rotY);
      const cosX  = Math.cos(tilY),  sinX  = Math.sin(tilY);
      const cosZ  = Math.cos(tilX),  sinZ  = Math.sin(tilX);

      // Project every node
      const proj = nodes.map(n => {
        // Y-axis rotation
        let rx = n.x * cosY + n.z * sinY;
        let ry = n.y;
        let rz = -n.x * sinY + n.z * cosY;
        // X-axis tilt (mouse Y)
        const ry2 = ry * cosX - rz * sinX;
        const rz2 = ry * sinX + rz * cosX;
        // Z-axis tilt (mouse X)
        const rx3 = rx * cosZ - ry2 * sinZ;
        const ry3 = rx * sinZ + ry2 * cosZ;
        return project(rx3, ry3, rz2, W, H);
      });

      // Gentle drift + boundary bounce
      nodes.forEach(n => {
        n.x += n.vx; n.y += n.vy; n.z += n.vz;
        const d = Math.hypot(n.x, n.y, n.z);
        if (d > 480) { n.vx *= -0.85; n.vy *= -0.85; n.vz *= -0.85; }
      });

      // ── Edges ─────────────────────────────────────────────
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const dx = proj[i].px - proj[j].px;
          const dy = proj[i].py - proj[j].py;
          const d  = Math.hypot(dx, dy);
          if (d < CONNECTION_PX) {
            const alpha = (1 - d / CONNECTION_PX) * 0.22
                          * Math.min(proj[i].scale, proj[j].scale) * 2;
            ctx.beginPath();
            ctx.moveTo(proj[i].px, proj[i].py);
            ctx.lineTo(proj[j].px, proj[j].py);
            ctx.strokeStyle = `rgba(255,255,255,${alpha.toFixed(3)})`;
            ctx.lineWidth = 0.6;
            ctx.stroke();
          }
        }
      }

      // ── Nodes ─────────────────────────────────────────────
      nodes.forEach((n, i) => {
        const { px, py, scale } = proj[i];
        const pulse  = n.big ? 0.65 + 0.35 * Math.sin(elapsed * 1.4 + n.phase) : 1;
        const radius = n.r * scale;
        const opacity = Math.min((0.35 + 0.65 * scale) * pulse, 1);

        if (n.big) {
          // Glow halo
          const grd = ctx.createRadialGradient(px, py, 0, px, py, radius * 4);
          grd.addColorStop(0,   `rgba(255,255,255,${(opacity * 0.55).toFixed(3)})`);
          grd.addColorStop(0.5, `rgba(255,255,255,${(opacity * 0.12).toFixed(3)})`);
          grd.addColorStop(1,   'rgba(255,255,255,0)');
          ctx.beginPath();
          ctx.arc(px, py, radius * 4, 0, Math.PI * 2);
          ctx.fillStyle = grd;
          ctx.fill();
        }

        ctx.beginPath();
        ctx.arc(px, py, Math.max(radius, 0.5), 0, Math.PI * 2);
        ctx.fillStyle = `rgba(255,255,255,${opacity.toFixed(3)})`;
        ctx.fill();
      });

      raf.current = requestAnimationFrame(tick);
    };

    raf.current = requestAnimationFrame(tick);

    return () => {
      cancelAnimationFrame(raf.current);
      ro.disconnect();
      window.removeEventListener('mousemove', onMove);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      className={className}
      style={{ width: '100%', height: '100%', display: 'block' }}
    />
  );
}
