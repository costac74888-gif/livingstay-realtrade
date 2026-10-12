/* Approved presentation, mounted as normal owned-preview pages, not a gallery.
 * Existing API-backed routes keep their original controllers and templates.
 * New visual flows do not claim account, payment or operational integration.
 */
import React from 'react';
import { createRoot } from 'react-dom/client';
import { ConsumerView } from '../artifacts/mockup-sandbox/src/components/mockups/hs2-complete/ConsumerViews';
import { LegacyView } from '../artifacts/mockup-sandbox/src/components/mockups/hs2-complete/LegacyViews';
import { AdminView, OwnerView } from '../artifacts/mockup-sandbox/src/components/mockups/hs2-complete/OperationsViews';
import { DetailView, syntheticPlaces, type Screen } from '../artifacts/mockup-sandbox/src/components/mockups/hs2-complete/_shared';

const boot = JSON.parse(document.getElementById('hs-design-bootstrap')!.textContent!);
const screens = boot.screens as Screen[];
const screen = screens.find(s => s.id === boot.screen);
if (!screen) throw new Error('Unknown preview page');
// Same owned demo item as the native search/detail. Never substitute a
// different mockup property's title/price when opening a detail popup.
if (boot.places?.length) syntheticPlaces.splice(0, syntheticPlaces.length, ...boot.places);
let view;
if (screen.id.startsWith('L')) view = <LegacyView screen={screen} allScreens={screens}/>;
else if (screen.role === '임대인') view = <OwnerView screen={screen}/>;
else if (screen.role === '관리자') view = <AdminView screen={screen}/>;
else if (['detail','detail-month','detail-missing'].includes(screen.view))
  view = <DetailView screen={screen} month={screen.view === 'detail-month'} missing={screen.view === 'detail-missing'}/>;
else view = <ConsumerView screen={screen}/>;
createRoot(document.getElementById('hs-design-page')!).render(view);
