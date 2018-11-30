#!/usr/bin/env python
# encoding: utf-8
import io
import sys
from typing import Callable, Any

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


class IndicatorEvaluationApplication(npyscreen.NPSAppManaged):
    def __init__(self, bundle: stix2.Bundle, *, on_save):
        self.bundle = bundle
        self.on_save = on_save
        self.identity = None
        super().__init__()

    def set_identity(self, identity: stix2.Identity):
        self.bundle.objects.append(identity)
        self.identity = identity

    def on_identity_selected(self, identity: stix2.Identity):
        self.set_identity(identity)

        self.switchForm('INDICATORS')

    def onStart(self):
        self.addForm('MAIN', IdentitySelectionForm, bundle=self.bundle)
        self.addForm('NEW_IDENTITY', IdentityEntryForm)
        self.addForm('INDICATORS', IndicatorSelectionForm, bundle=self.bundle)
        self.addForm('EVALUATION', IndicatorEvaluationForm, bundle=self.bundle, on_save=self.on_save)


class IdentitySelectionForm(CancelForm):
    OK_BUTTON_TEXT = 'Cancel'

    def __init__(self, *args, bundle: stix2.Bundle, **kwargs):
        self.bundle = bundle
        super().__init__(*args, **kwargs)

    def create(self):
        self.identity = self.add(
            IdentitySelection,
            bundle=self.bundle,
        )

    def on_cancel(self):
        sys.exit(0)


class IdentitySelection(npyscreen.MultiSelectAction):
    def __init__(self, *args, bundle: stix2.Bundle, **kwargs):
        self.bundle = bundle
        identities = [obj for obj in bundle.objects if obj.type == 'identity']
        kwargs['values'] = [None] + identities
        super().__init__(*args, **kwargs)

    def display_value(self, identity: stix2.Identity) -> str:
        if identity is None:
            return 'NEW IDENTITY'
        else:
            return (
                f'{identity.identity_class.title()}: {identity.name}\n'
                f'\t{identity.id}'
            )

    def get_identity(self) -> stix2.Identity:
        objects = self.get_selected_objects()
        if objects:
            (identity,) = objects
            return identity

    def actionHighlighted(self, act_on_this, key_press):
        identity = self.get_identity()
        parent_app: IndicatorEvaluationApplication = self.find_parent_app()

        if identity is None:
            parent_app.switchForm('NEW_IDENTITY')
        else:
            parent_app.on_identity_selected(identity)


class IdentityEntryForm(npyscreen.ActionForm):
    OK_BUTTON_TEXT = 'Use'

    def create(self):
        self.name = self.add(
            npyscreen.TitleText,
            name="What's your name?",
        )
        self.email = self.add(
            npyscreen.TitleText,
            name="What's your email address?",
        )

    def on_cancel(self):
        self.find_parent_app().switchForm('IDENTITIES')

    def on_ok(self):
        identity = stix2.Identity(
            identity_class='individual',
            name=self.name.value,
            contact_information=self.email.value,
        )

        parent_app: IndicatorEvaluationApplication = self.find_parent_app()
        parent_app.on_identity_selected(identity)


class IndicatorSelectionForm(CancelForm):
    OK_BUTTON_TEXT = 'Cancel'

    def __init__(self, name=None, parentApp=None, framed=None, help=None,
                 color='FORMDEFAULT', widget_list=None, cycle_widgets=False,
                 *args, bundle: stix2.Bundle, **keywords):
        indicators = [obj for obj in bundle.objects if obj.type == 'indicator']
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
        self.find_parent_app().switchForm('IDENTITIES')


class IndicatorSelection(npyscreen.MultiSelectAction):
    def display_value(self, indicator: stix2.Indicator) -> str:
        return f'{indicator.name}\n\t{indicator.id}'

    def actionHighlighted(self, indicator, key_press):
        # NOTE: this is a bit of a misnomer: "highlighted" is "pressed enter/space on"
        parent_app = self.find_parent_app()
        parent_app.getForm('EVALUATION').set_indicator(indicator)
        parent_app.switchForm('EVALUATION')


class IndicatorEvaluationForm(npyscreen.ActionForm):
    indicator: stix2.Indicator = None

    OK_BUTTON_TEXT = 'Save'

    def __init__(self,
                 *args,
                 bundle: stix2.Bundle,
                 indicator: stix2.Indicator = None,
                 on_save: Callable[[stix2.Opinion], Any],
                 **kwargs):
        self.bundle = bundle
        self.set_indicator(indicator)
        self.on_save = on_save
        super().__init__(*args, **kwargs)

    def set_indicator(self, indicator: stix2.Indicator):
        if indicator:
            self.indicator = indicator
            self.name = f'Evaluate Indicator: {self.indicator.name} {self.indicator.id}'

    def create(self):
        self.opinion = self.add(
            OpinionMenu,
            name='This indicator is effective. Do you agree or disagree?',
        )
        self.explanation = self.add(
            TitleMultiLineEdit,
            name='Why?',
            value='',
            rely=10,
        )

    def on_ok(self):
        opinion = stix2.Opinion(
            object_refs=[self.indicator],
            opinion=self.opinion.value,
            explanation=self.explanation.value,
        )
        self.bundle.objects.append(opinion)
        self.on_save(opinion)
        sys.exit(0)

    def on_cancel(self):
        parent_app = self.find_parent_app()
        parent_app.switchForm('MAIN')


class TitleMultiLineEdit(npyscreen.TitleText):
    _entry_type = npyscreen.MultiLineEdit


class OpinionSelectOne(npyscreen.SelectOne):
    def display_value(self, option):
        return option.replace('-', ' ').title()

    def get_opinion(self) -> str:
        (opinion,) = self.get_selected_objects()
        return opinion


class OpinionMenu(npyscreen.TitleSelectOne):
    _entry_type = OpinionSelectOne

    def __init__(self, *args, **kwargs):
        kwargs['values'] = stix2.Opinion._properties['opinion'].allowed
        super().__init__(*args, **kwargs)

    @property
    def value(self):
        if getattr(self, 'entry_widget', None):
            return self.entry_widget.get_opinion()

    @value.setter
    def value(self, value):
        self.set_value(value)


@click.command()
@click.option('-i', '--input', type=click.File('r'), required=True)
@click.option('-o', '--output', type=click.File('w'))
def judge_intel(input: io.FileIO, output: io.FileIO):
    if output is None:
        output = open(input.name, 'r+')

    bundle = stix2.parse(input, version='2.1')
    assert bundle.type == 'bundle'

    def add_opinion(opinion: stix2.Opinion):
        """Add opinion to the bundle"""

    def save_bundle():
        """Save bundle to the output file"""
        content = bundle.serialize(pretty=True)
        output.truncate()
        output.write(content)

    def handle_save(opinion: stix2.Opinion):
        add_opinion(opinion)
        save_bundle()

    app = IndicatorEvaluationApplication(bundle, on_save=handle_save)
    app.run()


if __name__ == '__main__':
    judge_intel()
