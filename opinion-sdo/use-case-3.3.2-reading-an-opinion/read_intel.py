#!/usr/bin/env python
# encoding: utf-8
import io
import sys
from typing import List

import click
import npyscreen
import stix2


class CancelForm(npyscreen.ActionFormMinimal):
    OK_BUTTON_TEXT = 'Cancel'

    def on_cancel(self):
        pass

    def on_ok(self):
        # our "OK button" is actually a cancel – it's just less work to do that
        # instead of a saner naming approach with npyscreen.
        self.on_cancel()


class IndicatorEvaluationReaderApplication(npyscreen.NPSAppManaged):
    def __init__(self, bundle: stix2.Bundle):
        self.store = stix2.MemoryStore(bundle)
        super().__init__()

    def onStart(self):
        self.addForm('MAIN', IndicatorSelectionForm, store=self.store)
        self.addForm('INDICATOR', IndicatorViewerForm, store=self.store)


class IndicatorSelectionForm(CancelForm):
    OK_BUTTON_TEXT = 'Done'

    def __init__(self, name=None, parentApp=None, framed=None, help=None,
                 color='FORMDEFAULT', widget_list=None, cycle_widgets=False,
                 *args, store: stix2.MemoryStore, **keywords):
        indicators = store.query([stix2.Filter('type', '=', 'indicator')])
        self._provided_indicators = tuple(indicators)
        super().__init__(name, parentApp, framed, help, color, widget_list,
                         cycle_widgets, *args, **keywords)

    def create(self):
        self.indicator: IndicatorSelection = self.add(
            IndicatorSelection,
            name='Choose an Indicator',
            values=self._provided_indicators
        )

    def on_cancel(self):
        sys.exit(0)


class IndicatorSelection(npyscreen.MultiSelectAction):
    def display_value(self, indicator: stix2.Indicator) -> str:
        return f'{indicator.name}\n\t{indicator.id}'

    def actionHighlighted(self, indicator, key_press):
        # NOTE: this is a bit of a misnomer: "highlighted" is "pressed enter/space on"
        parent_app = self.find_parent_app()
        parent_app.getForm('INDICATOR').set_indicator(indicator)
        parent_app.switchForm('INDICATOR')


class IndicatorViewerForm(npyscreen.ActionFormMinimal):
    indicator: stix2.Indicator = None
    opinions: List[stix2.Opinion] = None

    OK_BUTTON_TEXT = 'Return'

    def __init__(self,
                 *args,
                 store: stix2.MemoryStore,
                 indicator: stix2.Indicator = None,
                 **kwargs):
        self.store = store
        self.set_indicator(indicator)
        super().__init__(*args, **kwargs)

    def set_indicator(self, indicator: stix2.Indicator):
        if indicator:
            self.indicator = indicator
            self.buffer.name = f'Opinions: {self.indicator.name} ({self.indicator.id})'
            self.buffer.clearBuffer()

            opinions = self.store.query([
                stix2.Filter('type', '=', 'opinion'),
                stix2.Filter('object_refs', 'contains', self.indicator.id),
            ])
            opinions.sort(key=lambda opinion: opinion.created, reverse=True)

            for opinion in opinions:
                opinion: stix2.Opinion

                creator = self.store.creator_of(opinion)
                opinion_text = opinion.opinion.replace('-', ' ').title()
                evaluated_at = opinion.created.strftime('%Y-%m-%d %H:%M:%S')

                indent = '    '
                explanation = indent + '\n'.join(indent + line
                                                 for line in opinion.explanation.splitlines())

                self.buffer.buffer([
                    f'# {creator.name} ({creator.identity_class.title()})',
                    f'  Opinion on effectiveness: {opinion_text}',
                    f'  Evaluated at: {evaluated_at}',
                    f'',
                    f'{explanation}',
                    f'',
                    f'',
                ], scroll_end=False)

    def create(self):
        self.buffer: npyscreen.TitleBufferPager = self.add(
            npyscreen.TitleBufferPager,
            name='Opinions',
        )

    def on_ok(self):
        parent_app = self.find_parent_app()
        parent_app.switchForm('MAIN')


@click.command()
@click.option('-i', '--input', type=click.File('r'), required=True)
def judge_intel(input: io.FileIO):
    bundle = stix2.parse(input, version='2.1')
    assert bundle.type == 'bundle'

    app = IndicatorEvaluationReaderApplication(bundle)
    app.run()


if __name__ == '__main__':
    judge_intel()
